import pytest


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
async def test_internal_build_complete_creates_release_and_route(auth_client):
    project_id, _ = await _create_project(auth_client)
    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    headers = {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder",
    }

    running = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/status",
        json={"status": "running"},
        headers=headers,
    )
    assert running.status_code == 200

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
    assert body["release"]["release"]["build_id"] == build_id
    assert body["release"]["release"]["id"] == build.json()["planned_release_id"]
    assert body["release"]["route"]["hostname"].endswith(".apps.example.com")
