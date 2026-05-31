from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.celery_builder.runner import run_fake_build


@asynccontextmanager
async def build_control_plane_client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url.rstrip("/")) as client:
        yield client


async def run_fake_build_task(
    *,
    build_id: str,
    base_url: str,
    service_token: str,
    service_name: str,
    artifact_bucket: str,
    artifact_prefix: str | None = None,
    manifest_key: str | None = None,
    # not included in celery task args
    source_snapshot: dict[str, Any] | None = None,
    build_config: dict[str, Any] | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    async with build_control_plane_client(base_url) as client:
        return await run_fake_build(
            client,
            build_id=build_id,
            service_token=service_token,
            service_name=service_name,
            artifact_bucket=artifact_bucket,
            artifact_prefix=artifact_prefix,
            manifest_key=manifest_key,
            # not included in celery task args
            source_snapshot=source_snapshot,
            build_config=build_config,
            source_ref=source_ref,
        )
