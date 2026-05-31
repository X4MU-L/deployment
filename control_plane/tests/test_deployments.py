import pytest


async def _seed_build(auth_client) -> str:
    """Create a project + environment + build and return (build_id, env_id)."""
    proj = await auth_client.post("/api/v1/projects/", json={
        "name": "deploy-test", "repo_url": "https://github.com/ex/deploy",
    })
    project_id = proj.json()["id"]

    env = await auth_client.post("/api/v1/environments/", json={
        "project_id": project_id, "name": "production",
    })
    env_id = env.json()["id"]

    build = await auth_client.post("/api/v1/builds/", json={"project_id": project_id})
    build_id = build.json()["id"]

    # Advance build to succeeded
    await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "running"})
    await auth_client.patch(f"/api/v1/builds/{build_id}/transition", json={"status": "succeeded"})

    return build_id, env_id


@pytest.mark.asyncio
async def test_create_deployment(auth_client):
    build_id, env_id = await _seed_build(auth_client)
    resp = await auth_client.post("/api/v1/deployments/", json={
        "build_id": build_id, "environment_id": env_id,
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_deployment_transition_pending_to_healthy(auth_client):
    build_id, env_id = await _seed_build(auth_client)
    dep = await auth_client.post("/api/v1/deployments/", json={
        "build_id": build_id, "environment_id": env_id,
    })
    dep_id = dep.json()["id"]

    # pending → provisioning
    r = await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "provisioning"})
    assert r.json()["status"] == "provisioning"

    # provisioning → healthy
    r = await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "healthy"})
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_deployment_promoted(auth_client):
    build_id, env_id = await _seed_build(auth_client)
    dep = await auth_client.post("/api/v1/deployments/", json={
        "build_id": build_id, "environment_id": env_id,
    })
    dep_id = dep.json()["id"]

    await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "provisioning"})
    await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "healthy"})
    r = await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "promoted"})
    assert r.json()["status"] == "promoted"


@pytest.mark.asyncio
async def test_deployment_invalid_transition(auth_client):
    build_id, env_id = await _seed_build(auth_client)
    dep = await auth_client.post("/api/v1/deployments/", json={
        "build_id": build_id, "environment_id": env_id,
    })
    dep_id = dep.json()["id"]

    # pending → healthy is not allowed (must go through provisioning first)
    r = await auth_client.patch(f"/api/v1/deployments/{dep_id}/transition", json={"status": "healthy"})
    assert r.status_code == 422