import pytest

from app.artifact_store.r2 import R2ArtifactStore


def _service_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder",
    }


@pytest.mark.asyncio
async def test_route_resolution_tolerates_r2_artifact_store_stub(auth_client, monkeypatch):
    monkeypatch.setattr("app.core.dependencies._artifact_store", lambda: R2ArtifactStore())

    project = await auth_client.post(
        "/api/v1/projects/",
        json={"name": "release-r2-stub", "repo_url": "https://github.com/ex/rel"},
    )
    project_id = project.json()["id"]

    build = await auth_client.post(f"/api/v1/projects/{project_id}/builds", json={})
    build_id = build.json()["id"]

    completed = await auth_client.post(
        f"/api/v1/internal/builds/{build_id}/complete",
        json={
            "status": "succeeded",
            "artifact_ref": "r2://artifacts/projects/proj/releases/rel_1/",
            "manifest_ref": "r2://artifacts/projects/proj/releases/rel_1/manifest.json",
        },
        headers=_service_headers(),
    )
    assert completed.status_code == 200
    hostname = completed.json()["release"]["route"]["hostname"]

    resolved = await auth_client.get(
        "/api/v1/internal/routes/resolve",
        params={"hostname": hostname},
        headers=_service_headers(),
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["static_origin"]["r2_bucket"] == "artifacts"
    assert body["static_origin"]["r2_prefix"] == "projects/proj/releases/rel_1"
    assert body["static_origin"]["manifest_path"] == "projects/proj/releases/rel_1/manifest.json"
    assert body["static_origin"]["index_document"] == "index.html"
