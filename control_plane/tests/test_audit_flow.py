import pytest
from sqlalchemy import select

from app.db.models.audit_event import AuditEvent


def _service_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder",
    }


@pytest.mark.asyncio
async def test_project_build_and_release_emit_audit_events(auth_client, db_session):
    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "audit-test", "repo_url": "https://github.com/ex/audit"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/complete",
        json={
            "status": "succeeded",
            "artifact_ref": "r2://artifacts/projects/proj/releases/rel_1/",
            "manifest_ref": "r2://artifacts/projects/proj/releases/rel_1/manifest.json",
        },
        headers=_service_headers(),
    )

    rows = await db_session.execute(select(AuditEvent).order_by(AuditEvent.created_at))
    actions = [row.action for row in rows.scalars().all()]
    assert "project.created" in actions
    assert "build.triggered" in actions
    assert "build.succeeded" in actions
    assert "release.activated" in actions
