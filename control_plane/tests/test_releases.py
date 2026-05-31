import pytest


def _service_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder",
    }


async def _seed_release(auth_client):
    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "release-test", "repo_url": "https://github.com/ex/rel"},
    )
    project_id = project.json()["id"]

    envs = await auth_client.get(f"/api/v1/projects/{project_id}/environments")
    env_id = envs.json()[0]["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/status",
        json={"status": "running"},
        headers=_service_headers(),
    )
    completed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/complete",
        json={
            "status": "succeeded",
            "artifact_ref": "r2://artifacts/projects/proj/releases/rel_1/",
            "manifest_ref": "r2://artifacts/projects/proj/releases/rel_1/manifest.json",
        },
        headers=_service_headers(),
    )
    body = completed.json()
    return project_id, env_id, build_id, body["release"]["release"]["id"], body["release"]["route"]["hostname"]


@pytest.mark.asyncio
async def test_get_release(auth_client):
    _, _, _, release_id, _ = await _seed_release(auth_client)
    resp = await auth_client.get(f"/api/v1/releases/{release_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == release_id
    assert resp.json()["build_id"]


@pytest.mark.asyncio
async def test_list_routes_for_release(auth_client):
    _, _, _, release_id, hostname = await _seed_release(auth_client)
    routes = await auth_client.get(f"/api/v1/releases/{release_id}/routes")
    assert routes.status_code == 200
    assert routes.json()[0]["hostname"] == hostname


@pytest.mark.asyncio
async def test_internal_route_resolution(auth_client):
    _, _, _, release_id, hostname = await _seed_release(auth_client)
    resp = await auth_client.get(
        "/api/v1/internal/routes/resolve",
        params={"hostname": hostname},
        headers=_service_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["release_id"] == release_id
    assert body["route_kind"] == "static"
    assert body["static_origin"]["index_document"] == "index.html"
