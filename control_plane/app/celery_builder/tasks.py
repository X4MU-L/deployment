from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

from celery.result import AsyncResult

from app.celery_builder.celery_app import celery_app
from app.celery_builder.execution import run_fake_build_task
from app.core.config import get_settings


@celery_app.task(name="celery_builder.process_build")
def _process_build_task(build_id: str) -> dict[str, Any]:
    settings = get_settings()
    return _run_async(
        _run_fake_build_task(
            build_id=build_id,
            base_url=settings.celery_builder_base_url,
            service_token=settings.internal_service_token,
            service_name=settings.celery_builder_service_name,
            artifact_bucket=settings.celery_builder_artifact_bucket,
            artifact_prefix=None,
            manifest_key=None,
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


_run_fake_build_task = run_fake_build_task


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
