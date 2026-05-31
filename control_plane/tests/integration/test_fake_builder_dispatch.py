import pytest
from sqlalchemy import select

from app.cloudflare_builder.builder import CFBuilder, CloudflareQueueDispatch
from app.db.models.audit_event import AuditEvent
from app.db.models.build import Build


@pytest.mark.asyncio
async def test_trigger_build_enqueues_fake_builder_job(auth_client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.celery_builder.builder.get_settings",
        lambda: type("Settings", (), {"celery_builder_queue_name": "fake-builder"})(),
    )
    monkeypatch.setattr(
        "app.celery_builder.builder.ProcessBuildTask.apply_async",
        lambda build_id, queue: type("AsyncResult", (), {"id": "celery-job-1"})(),
    )

    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "dispatch-app", "repo_url": "https://github.com/example/dispatch-app"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    assert build.status_code == 201
    build_body = build.json()

    assert build_body["builder_adapter"] == "celery"
    assert build_body["queue_job_id"] == "celery-job-1"

    rows = await db_session.execute(select(AuditEvent).order_by(AuditEvent.created_at))
    actions = [row.action for row in rows.scalars().all()]
    assert "build.triggered" in actions
    assert "build.enqueued" in actions

    stored_build = await db_session.get(Build, build_body["id"])
    assert stored_build.builder_adapter == "celery"
    assert stored_build.queue_job_id == "celery-job-1"


@pytest.mark.asyncio
async def test_trigger_build_returns_503_when_dispatch_fails(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.celery_builder.builder.get_settings",
        lambda: type("Settings", (), {"celery_builder_queue_name": "fake-builder"})(),
    )
    monkeypatch.setattr(
        "app.celery_builder.builder.ProcessBuildTask.apply_async",
        lambda build_id, queue: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )

    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "dispatch-fail", "repo_url": "https://github.com/example/dispatch-fail"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    assert build.status_code == 503
    assert build.json()["detail"]["code"] == "BUILD_DISPATCH_FAILED"


@pytest.mark.asyncio
async def test_trigger_build_uses_cloudflare_stub_from_factory(auth_client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.core.dependencies.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "background_builder_provider": "cloudflare",
                "cloudflare_queue_name": "build-requested",
                "cloudflare_artifact_bucket": "static-artifacts",
            },
        )(),
    )

    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "cf-app", "repo_url": "https://github.com/example/cf-app"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    assert build.status_code == 503
    assert build.json()["detail"]["code"] == "BUILD_DISPATCH_FAILED"

    rows = await db_session.execute(select(Build).order_by(Build.created_at.desc()))
    stored_build = rows.scalars().first()
    assert stored_build is not None
    assert stored_build.builder_adapter == "cloudflare"
    assert stored_build.queue_job_id is None
    assert stored_build.planned_release_id is not None
    assert stored_build.status == "failed"


@pytest.mark.asyncio
async def test_trigger_build_produces_build_requested_v1_payload_for_cloudflare(auth_client, monkeypatch):
    dispatched: list[CloudflareQueueDispatch] = []

    class _Producer:
        def publish(self, dispatch: CloudflareQueueDispatch) -> str | None:
            dispatched.append(dispatch)
            return "cf-job-1"

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

    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "cf-dispatch-app", "repo_url": "https://github.com/example/cf-dispatch-app"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    assert build.status_code == 201
    body = build.json()

    assert body["builder_adapter"] == "cloudflare"
    assert body["queue_job_id"] == "cf-job-1"
    assert body["planned_release_id"]
    assert len(dispatched) == 1
    assert dispatched[0].queue_name == "build-requested"
    assert '"schema":"build.requested.v1"' in dispatched[0].payload
    assert f'"release_id":"{body["planned_release_id"]}"' in dispatched[0].payload
    assert (
        f'"prefix":"projects/{project_id}/releases/{body["planned_release_id"]}"'
        in dispatched[0].payload
    )


@pytest.mark.asyncio
async def test_internal_build_lookup_requires_service_auth(auth_client):
    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "lookup-app", "repo_url": "https://github.com/example/lookup-app"},
    )
    project_id = project.json()["id"]
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    denied = await auth_client.get(f"/api/v1/internal/builds/{build_id}")
    assert denied.status_code == 401
