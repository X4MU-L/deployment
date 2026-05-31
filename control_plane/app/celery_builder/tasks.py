from __future__ import annotations

import asyncio
import queue
import threading
from contextlib import asynccontextmanager
from typing import Any

import httpx
from celery.result import AsyncResult

from app.celery_builder.celery_app import celery_app
from app.celery_builder.runner import run_fake_build
from app.core.config import get_settings


@asynccontextmanager
async def build_control_plane_client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url.rstrip("/")) as client:
        yield client


@celery_app.task(name="fake_builder.process_build")
def _process_build_task(build_id: str) -> dict[str, Any]:
    settings = get_settings()
    return _run_async(
        _run_fake_build_task(
            build_id=build_id,
            base_url=settings.fake_builder_base_url,
            service_token=settings.internal_service_token,
            service_name=settings.fake_builder_service_name,
            artifact_bucket=settings.fake_builder_artifact_bucket,
        )
    )


class ProcessBuildTask:
    """Type-safe wrapper for the Celery task."""

    @staticmethod
    def delay(build_id: str) -> AsyncResult:
        return _process_build_task.delay(build_id)

    @staticmethod
    def apply_async(build_id: str, queue: str) -> AsyncResult:
        return _process_build_task.apply_async(args=(build_id,), queue=queue)


async def _run_fake_build_task(
    *,
    build_id: str,
    base_url: str,
    service_token: str,
    service_name: str,
    artifact_bucket: str,
) -> dict[str, Any]:
    async with build_control_plane_client(base_url) as client:
        return await run_fake_build(
            client,
            build_id=build_id,
            service_token=service_token,
            service_name=service_name,
            artifact_bucket=artifact_bucket,
        )


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put((True, asyncio.run(coro)))
        except Exception as exc:  # pragma: no cover - exercised via eager task failures
            result_queue.put((False, exc))

    thread = threading.Thread(target=_runner, name="fake-builder-task-runner", daemon=True)
    thread.start()
    thread.join()
    ok, value = result_queue.get()
    if ok:
        return value
    raise value
