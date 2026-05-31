import json
from pathlib import Path

import pytest


def _service_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-internal-service-token",
        "X-Service-Name": "builder",
    }


def _write_manifest(local_artifact_store_root, *, bucket: str, key: str, index_document: str) -> None:
    target = Path(local_artifact_store_root) / bucket / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema": "static_release_manifest.v1",
                "project_id": "proj",
                "release_id": "rel_1",
                "build_id": "build_1",
                "generated_at": "2026-05-31T12:10:00Z",
                "index_document": index_document,
                "error_document": None,
                "cache_policy": {
                    "html_max_age_seconds": 30,
                    "asset_max_age_seconds": 31536000,
                    "asset_cache_control": "public, max-age=31536000, immutable",
                },
                "assets": [
                    {"path": index_document, "sha256": "abc", "content_type": "text/html"},
                ],
            }
        ),
        encoding="utf-8",
    )


async def _seed_release(auth_client, local_artifact_store_root, *, index_document: str = "index.html"):
    _write_manifest(
        local_artifact_store_root,
        bucket="artifacts",
        key="projects/proj/releases/rel_1/manifest.json",
        index_document=index_document,
    )
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
async def test_get_release(auth_client, local_artifact_store_root):
    _, _, _, release_id, _ = await _seed_release(auth_client, local_artifact_store_root)
    resp = await auth_client.get(f"/api/v1/releases/{release_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == release_id
    assert resp.json()["build_id"]


@pytest.mark.asyncio
async def test_list_routes_for_release(auth_client, local_artifact_store_root):
    _, _, _, release_id, hostname = await _seed_release(auth_client, local_artifact_store_root)
    routes = await auth_client.get(f"/api/v1/releases/{release_id}/routes")
    assert routes.status_code == 200
    assert routes.json()[0]["hostname"] == hostname


@pytest.mark.asyncio
async def test_internal_route_resolution(auth_client, local_artifact_store_root):
    _, _, _, release_id, hostname = await _seed_release(
        auth_client,
        local_artifact_store_root,
        index_document="app.html",
    )
    resp = await auth_client.get(
        "/api/v1/internal/routes/resolve",
        params={"hostname": hostname},
        headers=_service_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["release_id"] == release_id
    assert body["route_kind"] == "static"
    assert body["static_origin"]["r2_bucket"] == "artifacts"
    assert body["static_origin"]["r2_prefix"] == "projects/proj/releases/rel_1"
    assert body["static_origin"]["manifest_path"] == "projects/proj/releases/rel_1/manifest.json"
    assert body["static_origin"]["index_document"] == "app.html"
