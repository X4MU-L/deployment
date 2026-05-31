import pytest
from sqlalchemy import select

from app.db.models.build import Build as BuildModel


async def _create_project(auth_client) -> str:
    resp = await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "build-test",
            "repo_url": "https://github.com/ex/build",
        },
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_build(auth_client):
    project_id = await _create_project(auth_client)
    resp = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == project_id
    assert body["status"] == "queued"
    assert "correlation_id" in body


@pytest.mark.asyncio
async def test_build_transition_queued_to_running(auth_client):
    project_id = await _create_project(auth_client)
    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]
    resp = await auth_client.patch(
        f"/api/v1/builds/{build_id}/transition", json={"status": "running"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_build_transition_queued_to_succeeded_fails(auth_client):
    """Cannot skip 'running' — must go queued → running → succeeded."""
    project_id = await _create_project(auth_client)
    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]
    resp = await auth_client.patch(
        f"/api/v1/builds/{build_id}/transition", json={"status": "succeeded"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_build_full_lifecycle(auth_client):
    project_id = await _create_project(auth_client)
    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]

    # queued → running
    r = await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "running"})
    assert r.json()["status"] == "running"

    # running → succeeded
    r = await auth_client.patch(
        f"/api/v1/builds/{build_id}/transition",
        json={
            "status": "succeeded",
            "artifact_ref": "s3://bucket/artifact.tar.gz",
        },
    )
    assert r.json()["status"] == "succeeded"
    assert r.json()["artifact_ref"] == "s3://bucket/artifact.tar.gz"


@pytest.mark.asyncio
async def test_build_cancel(auth_client):
    project_id = await _create_project(auth_client)
    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]

    r = await auth_client.patch(
        f"/api/v1/builds/{build_id}/transition", json={"status": "canceled"}
    )
    assert r.json()["status"] == "canceled"


@pytest.mark.asyncio
async def test_terminal_state_rejects_transition(auth_client):
    project_id = await _create_project(auth_client)
    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]

    # queued → running → succeeded
    await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "running"})
    await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "succeeded"})

    # succeeded is terminal — no further transitions
    r = await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "running"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_build_with_source_and_config_metadata(auth_client, db_session):
    project_id = await _create_project(auth_client)
    payload = {
        "project_id": project_id,
        "job_type": "build",
        "source_ref": "refs/heads/main",
        "commit_sha": "abc123def456",
        "source_snapshot": {
            "repository_id": "repo_123",
            "full_name": "acme/build-test",
            "branch": "main",
        },
        "build_config": {
            "root_directory": "apps/web",
            "install_command": "pnpm install",
            "build_command": "pnpm build",
            "output_directory": ".next",
        },
        "env_snapshot": {
            "NODE_ENV": "production",
            "API_URL": "https://api.example.com",
        },
    }

    resp = await auth_client.post("/api/v1/builds/", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_type"] == "build"
    assert body["source_ref"] == "refs/heads/main"
    assert body["build_config"]["build_command"] == "pnpm build"
    assert body["env_snapshot"]["NODE_ENV"] == "production"

    row = await db_session.execute(select(BuildModel).where(BuildModel.id == body["id"]))
    build = row.scalar_one()
    assert build.commit_sha == "abc123def456"
    assert build.source_snapshot["repository_id"] == "repo_123"
