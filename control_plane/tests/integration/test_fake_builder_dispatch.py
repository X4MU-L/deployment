from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models.audit_event import AuditEvent
from app.db.models.build import Build


@pytest.mark.asyncio
async def test_trigger_build_enqueues_fake_builder_job(auth_client, db_session, monkeypatch):
    captured: dict[str, object] = {}

    def _fake_enqueue_build(build_id: str) -> str:
        captured["build_id"] = build_id
        return "celery-job-1"

    monkeypatch.setattr(
        "app.core.dependencies._fake_builder_dispatcher",
        lambda: SimpleNamespace(enqueue_build=_fake_enqueue_build),
    )

    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "dispatch-app", "repo_url": "https://github.com/example/dispatch-app"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    assert build.status_code == 201
    build_body = build.json()

    assert captured["build_id"] == build_body["id"]
    assert build_body["queue_job_id"] == "celery-job-1"

    rows = await db_session.execute(select(AuditEvent).order_by(AuditEvent.created_at))
    actions = [row.action for row in rows.scalars().all()]
    assert "build.triggered" in actions
    assert "build.enqueued" in actions

    stored_build = await db_session.get(Build, build_body["id"])
    assert stored_build.queue_job_id == "celery-job-1"


@pytest.mark.asyncio
async def test_trigger_build_returns_503_when_dispatch_fails(auth_client, monkeypatch):
    def _fake_enqueue_build(build_id: str) -> str:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(
        "app.core.dependencies._fake_builder_dispatcher",
        lambda: SimpleNamespace(enqueue_build=_fake_enqueue_build),
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
