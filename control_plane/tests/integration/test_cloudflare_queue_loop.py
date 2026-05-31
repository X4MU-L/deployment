import base64
import json
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.cloudflare_builder.builder import CFBuilder, CloudflareQueueDispatch
from app.cloudflare_builder.pull_consumer import CloudflarePullConsumer, FakeBuildMessageHandler, PulledMessage
from app.core.config import settings
from app.core.dependencies import get_db
from app.db.models.build import Build
from app.db.models.release import Release, Route
from app.main import app
from tests.conftest import TestSessionFactory


@pytest.fixture
def cloudflare_e2e_client_factory():
    @asynccontextmanager
    async def _factory(base_url: str):
        previous_override = app.dependency_overrides.get(get_db)

        async def _override_get_db():
            async with TestSessionFactory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=base_url,
            ) as client:
                yield client
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override

    return _factory


@pytest.mark.asyncio
async def test_cloudflare_build_requested_message_can_complete_full_build_flow(
    client,
    db_session,
    monkeypatch,
    local_artifact_store_root,
    cloudflare_e2e_client_factory,
):
    previous_override = app.dependency_overrides.get(get_db)

    async def _override_get_db():
        async with TestSessionFactory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    dispatched_payloads: list[str] = []

    try:
        class _Producer:
            def publish(self, dispatch: CloudflareQueueDispatch) -> str | None:
                dispatched_payloads.append(dispatch.payload)
                return None

        monkeypatch.setattr(
            "app.core.dependencies._background_builder",
            lambda: CFBuilder(producer=_Producer()),
        )
        monkeypatch.setattr(
            "app.cloudflare_builder.builder.get_settings",
            lambda: type(
                "Settings",
                (),
                {
                    "cloudflare_queue_name": "build-requested",
                    "cloudflare_artifact_bucket": "static-artifacts",
                },
            )(),
        )
        monkeypatch.setattr(
            "app.celery_builder.execution.build_control_plane_client",
            cloudflare_e2e_client_factory,
        )

        register = await client.post(
            "/api/v1/auth/register/password",
            json={"email": "cloudflare-e2e@example.com", "password": "secret123"},
        )
        assert register.status_code == 201

        login = await client.post(
            "/api/v1/auth/login/password",
            json={"email": "cloudflare-e2e@example.com", "password": "secret123"},
        )
        assert login.status_code == 200
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        project = await client.post(
            "/api/v1/projects/",
            json={
                "name": "cf-e2e-app",
                "repo_url": "https://github.com/example/cf-e2e-app",
                "build_settings": {
                    "install_command": "npm install",
                    "build_command": "npm run build",
                    "output_directory": "dist",
                },
            },
        )
        project_id = project.json()["id"]

        trigger = await client.post(f"/api/v1/projects/{project_id}/builds", json={})
        assert trigger.status_code == 201
        build_body = trigger.json()
        build_id = build_body["id"]
        planned_release_id = build_body["planned_release_id"]

        assert build_body["builder_adapter"] == "cloudflare"
        assert build_body["queue_job_id"] is None
        assert len(dispatched_payloads) == 1

        queue_payload = json.loads(dispatched_payloads[0])
        queue_payload["artifact_target"]["prefix"] = (
            f"custom-targets/{project_id}/releases/{planned_release_id}/site"
        )
        queue_payload["artifact_target"]["manifest_key"] = (
            f"{queue_payload['artifact_target']['prefix']}/static_release_manifest.v1.json"
        )
        queue_payload["git_checkout"]["source_ref"] = "refs/heads/release"
        queue_payload["build_spec"]["output_directory"] = "public-dist"
        encoded_body = base64.b64encode(json.dumps(queue_payload).encode("utf-8")).decode("utf-8")

        class _QueueClient:
            def __init__(self):
                self.acks = None

            def pull_messages(self, *, batch_size: int, visibility_timeout_ms: int):
                return [
                    PulledMessage(
                        body=encoded_body,
                        id="msg-1",
                        timestamp_ms=1710950954154,
                        attempts=1,
                        lease_id="lease-1",
                        metadata={"CF-Content-Type": "json"},
                    )
                ]

            def acknowledge(self, *, acks: list[str], retries: list[str]):
                self.acks = {"acks": acks, "retries": retries}
                return {"success": True}

        handler = FakeBuildMessageHandler(
            base_url="http://test",
            service_token="dev-internal-service-token",
            service_name="cloudflare-builder-worker",
        )
        consumer = CloudflarePullConsumer(
            queue_client=_QueueClient(),
            handler=handler,
            batch_size=5,
            visibility_timeout_ms=30000,
        )

        processed = consumer.run_once()
        assert processed == 1
        assert consumer._queue_client.acks == {"acks": ["lease-1"], "retries": []}

        build_status = await client.get(f"/api/v1/builds/{build_id}")
        assert build_status.status_code == 200
        assert build_status.json()["status"] == "succeeded"
        assert build_status.json()["planned_release_id"] == planned_release_id

        build_logs = await client.get(f"/api/v1/builds/{build_id}/logs")
        assert build_logs.status_code == 200
        log_text = "\n".join(line["content"] for line in build_logs.json())
        assert "checkout ref: refs/heads/release" in log_text
        assert "output: simulated static files generated in public-dist" in log_text

        release = await client.get(f"/api/v1/builds/{build_id}/release")
        assert release.status_code == 200
        release_body = release.json()
        assert release_body["id"] == planned_release_id
        assert release_body["artifact_ref"] == (
            f"r2://static-artifacts/{queue_payload['artifact_target']['prefix']}"
        )
        assert release_body["manifest_ref"] == (
            f"r2://static-artifacts/{queue_payload['artifact_target']['manifest_key']}"
        )

        route_resolution = await client.get(
            "/api/v1/internal/routes/resolve",
            params={"hostname": f"cf-e2e-app-{project_id[:8]}.{settings.apps_base_domain}"},
            headers={
                "Authorization": "Bearer dev-internal-service-token",
                "X-Service-Name": "routing-worker",
            },
        )
        assert route_resolution.status_code == 200
        assert route_resolution.json()["release_id"] == planned_release_id
        assert (
            route_resolution.json()["static_origin"]["r2_prefix"]
            == queue_payload["artifact_target"]["prefix"]
        )
        assert (
            route_resolution.json()["static_origin"]["manifest_path"]
            == queue_payload["artifact_target"]["manifest_key"]
        )

        build_row = (
            await db_session.execute(select(Build).where(Build.id == build_id))
        ).scalar_one()
        release_row = (
            await db_session.execute(select(Release).where(Release.id == planned_release_id))
        ).scalar_one()
        route_row = (
            await db_session.execute(select(Route).where(Route.release_id == planned_release_id))
        ).scalar_one()
        assert build_row.status == "succeeded"
        assert release_row.build_id == build_id
        assert route_row.hostname.endswith(f".{settings.apps_base_domain}")
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
