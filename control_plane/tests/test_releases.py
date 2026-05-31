import pytest


async def _seed_deployment(auth_client):
    """Create a full chain: project → env → build → deployment (promoted)."""
    proj = await auth_client.post("/api/v1/projects/", json={
        "name": "release-test", "repo_url": "https://github.com/ex/rel",
    })
    project_id = proj.json()["id"]

    env = await auth_client.post("/api/v1/environments/", json={
        "project_id": project_id, "name": "production",
    })
    env_id = env.json()["id"]

    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]
    await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "running"})
    await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "succeeded"})

    dep = await auth_client.post("/api/v1/deployments/", json={
        "build_id": build_id, "environment_id": env_id,
    })
    dep_id = dep.json()["id"]
    await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "provisioning"})
    await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "healthy"})
    await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "promoted"})

    return project_id, env_id, dep_id


@pytest.mark.asyncio
async def test_create_release(auth_client):
    project_id, env_id, dep_id = await _seed_deployment(auth_client)
    resp = await auth_client.post("/api/v1/releases/", json={
        "project_id": project_id,
        "environment_id": env_id,
        "deployment_id": dep_id,
    })
    assert resp.status_code == 201
    assert resp.json()["deployment_id"] == dep_id


@pytest.mark.asyncio
async def test_create_route(auth_client):
    project_id, env_id, dep_id = await _seed_deployment(auth_client)

    release = await auth_client.post("/api/v1/releases/", json={
        "project_id": project_id, "environment_id": env_id, "deployment_id": dep_id,
    })
    release_id = release.json()["id"]

    route = await auth_client.post("/api/v1/releases/routes/", json={
        "hostname": "app.example.com", "release_id": release_id,
    })
    assert route.status_code == 201
    assert route.json()["hostname"] == "app.example.com"


@pytest.mark.asyncio
async def test_duplicate_route_rejected(auth_client):
    project_id, env_id, dep_id = await _seed_deployment(auth_client)
    release = await auth_client.post("/api/v1/releases/", json={
        "project_id": project_id, "environment_id": env_id, "deployment_id": dep_id,
    })
    release_id = release.json()["id"]

    payload = {"hostname": "dup.example.com", "release_id": release_id}
    await auth_client.post("/api/v1/releases/routes/", json=payload)
    resp = await auth_client.post("/api/v1/releases/routes/", json=payload)
    assert resp.status_code == 409