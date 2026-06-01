from datetime import datetime, timedelta

import pytest

from app.db.models.build import Build


async def _create_project(auth_client) -> tuple[str, str]:
    project = await auth_client.post(
        "/api/v1/projects/",
        json={
            "name": "build-test",
            "repo_url": "https://github.com/ex/build",
            "default_branch": "main",
            "build_settings": {
                "root_directory": "apps/web",
                "install_command": "pnpm install",
                "build_command": "pnpm build",
                "output_directory": "dist",
            },
        },
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    envs = await auth_client.get(f"/api/v1/projects/{project_id}/environments")
    assert envs.status_code == 200
    assert len(envs.json()) == 1
    return project_id, envs.json()[0]["id"]


@pytest.mark.asyncio
async def test_create_project_creates_default_environment(auth_client):
    project_id, env_id = await _create_project(auth_client)
    assert project_id
    assert env_id


@pytest.mark.asyncio
async def test_trigger_build_uses_project_scope_and_snapshots(auth_client):
    project_id, env_id = await _create_project(auth_client)

    resp = await auth_client.post(
        f"/api/v1/projects/{project_id}/builds",
        json={"environment_name": "production", "source_ref": "refs/heads/main"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == project_id
    assert body["environment_id"] == env_id
    assert body["trigger_source"] == "user"
    assert body["triggered_by_user_id"]
    assert body["planned_release_id"]
    assert body["build_config"]["build_command"] == "pnpm build"
    assert body["source_snapshot"]["repo_url"] == "https://github.com/ex/build"
    assert body["source_snapshot"]["project_name"] == "build-test"


@pytest.mark.asyncio
async def test_get_build_requires_owner(auth_client, client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    reg = await client.post(
        "/api/v1/auth/register/password",
        json={"email": "other@example.com", "password": "secret123"},
    )
    assert reg.status_code == 201
    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "other@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    forbidden = await client.get(f"/api/v1/builds/{build_id}")
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_internal_build_status_requires_service_token(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    denied = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/status",
        json={"status": "running"},
    )
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_internal_build_claim_requires_service_token(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    denied = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 900},
    )
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_internal_build_claim_sets_running_lease_and_rejects_second_service(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    first_headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-a",
    }
    second_headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-b",
    }

    claimed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 120},
        headers=first_headers,
    )
    assert claimed.status_code == 200
    claimed_body = claimed.json()
    assert claimed_body["claimed"] is True
    assert claimed_body["build"]["status"] == "running"
    assert claimed_body["build"]["claimed_by_service"] == "builder-a"
    assert claimed_body["build"]["claim_expires_at"] is not None

    denied = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 120},
        headers=second_headers,
    )
    assert denied.status_code == 200
    denied_body = denied.json()
    assert denied_body["claimed"] is False
    assert denied_body["reason"] == "lease_active"
    assert denied_body["build"]["claimed_by_service"] == "builder-a"


@pytest.mark.asyncio
async def test_internal_build_claim_renew_extends_same_service_lease(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-a",
    }

    claimed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 60},
        headers=headers,
    )
    assert claimed.status_code == 200
    initial_expiry = claimed.json()["build"]["claim_expires_at"]

    renewed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim/renew",
        json={"lease_seconds": 180},
        headers=headers,
    )
    assert renewed.status_code == 200
    renewed_body = renewed.json()
    assert renewed_body["claimed"] is True
    assert renewed_body["build"]["claimed_by_service"] == "builder-a"
    assert renewed_body["build"]["claim_expires_at"] > initial_expiry


@pytest.mark.asyncio
async def test_internal_build_claim_renew_rejects_non_owner(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    owner_headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-a",
    }
    other_headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-b",
    }

    claimed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 120},
        headers=owner_headers,
    )
    assert claimed.status_code == 200

    renewed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim/renew",
        json={"lease_seconds": 120},
        headers=other_headers,
    )
    assert renewed.status_code == 200
    renewed_body = renewed.json()
    assert renewed_body["claimed"] is False
    assert renewed_body["reason"] == "not_claim_owner"


@pytest.mark.asyncio
async def test_internal_build_claim_allows_after_lease_expired(auth_client, db_session):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    owner_headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-a",
    }
    other_headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-b",
    }

    claimed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 60},
        headers=owner_headers,
    )
    assert claimed.status_code == 200
    assert claimed.json()["claimed"] is True

    db_build = await db_session.get(Build, build_id)
    db_build.claim_expires_at = datetime.utcnow() - timedelta(seconds=5)
    await db_session.flush()

    reclaimed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 120},
        headers=other_headers,
    )
    assert reclaimed.status_code == 200
    reclaimed_body = reclaimed.json()
    assert reclaimed_body["claimed"] is True
    assert reclaimed_body["build"]["claimed_by_service"] == "builder-b"


@pytest.mark.asyncio
async def test_internal_build_claim_renew_rejects_expired_lease(auth_client, db_session):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder-a",
    }

    claimed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 60},
        headers=headers,
    )
    assert claimed.status_code == 200
    assert claimed.json()["claimed"] is True

    db_build = await db_session.get(Build, build_id)
    db_build.claim_expires_at = datetime.utcnow() - timedelta(seconds=5)
    await db_session.flush()

    renewed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim/renew",
        json={"lease_seconds": 120},
        headers=headers,
    )
    assert renewed.status_code == 200
    renewed_body = renewed.json()
    assert renewed_body["claimed"] is False
    assert renewed_body["reason"] == "lease_expired"


@pytest.mark.asyncio
async def test_internal_build_complete_creates_release_and_route(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder",
    }

    running = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/claim",
        json={"lease_seconds": 900},
        headers=headers,
    )
    assert running.status_code == 200
    assert running.json()["claimed"] is True
    assert running.json()["build"]["status"] == "running"

    completed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/complete",
        json={
            "status": "succeeded",
            "artifact_ref": "r2://artifacts/projects/proj/releases/rel_1/",
            "manifest_ref": "r2://artifacts/projects/proj/releases/rel_1/manifest.json",
        },
        headers=headers,
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["build"]["status"] == "succeeded"
    assert body["build"]["claimed_by_service"] is None
    assert body["build"]["claim_expires_at"] is None
    assert body["release"]["release"]["build_id"] == build_id
    assert body["release"]["release"]["id"] == build.json()["planned_release_id"]
    assert body["release"]["route"]["hostname"].endswith(".apps.example.com")
