from __future__ import annotations

from urllib.parse import urlparse

import httpx


async def run_fake_build(
    client: httpx.AsyncClient,
    *,
    build_id: str,
    service_token: str,
    service_name: str = "fake-builder",
    artifact_bucket: str = "fake-static-artifacts",
) -> dict:
    headers = {
        "Authorization": f"Bearer {service_token}",
        "X-Service-Name": service_name,
    }
    build = (
        (await client.get(f"/api/v1/internal/builds/{build_id}", headers=headers))
        .raise_for_status()
        .json()
    )
    project_id = build["project_id"]
    source_snapshot = build.get("source_snapshot") or {}
    repo_url = source_snapshot.get("repo_url") or ""
    source_ref = build.get("source_ref") or source_snapshot.get("default_branch") or "main"

    supported, reason = _is_supported_public_github_repo(build, repo_url)
    status_response = await client.post(
        f"/api/v1/internal/builds/{build_id}/status",
        headers=headers,
        json={"status": "running"},
    )
    status_response.raise_for_status()

    log_lines = [
        f"fake-builder: received build {build_id}",
        f"source: {repo_url or 'unknown'}",
        f"checkout ref: {source_ref}",
    ]
    if supported:
        log_lines.extend(
            [
                "repo visibility: assumed public",
                "install: simulated dependency install completed",
                "build: simulated static site build completed",
                "upload: simulated artifact manifest prepared",
            ]
        )
    else:
        log_lines.extend(
            [
                "repo visibility: unsupported for fake builder",
                f"error: {reason}",
            ]
        )

    for index, line in enumerate(log_lines):
        log_response = await client.post(
            f"/api/v1/internal/builds/{build_id}/logs",
            headers=headers,
            json={"stream": "stdout", "lines": [line], "start_seq": index},
        )
        log_response.raise_for_status()

    if not supported:
        return (
            (
                await client.post(
                    f"/api/v1/internal/builds/{build_id}/complete",
                    headers=headers,
                    json={"status": "failed", "error_message": reason},
                )
            )
            .raise_for_status()
            .json()
        )

    artifact_ref = f"r2://{artifact_bucket}/projects/{project_id}/builds/{build_id}/site"
    manifest_ref = f"{artifact_ref}/static_release_manifest.v1.json"
    return (
        (
            await client.post(
                f"/api/v1/internal/builds/{build_id}/complete",
                headers=headers,
                json={
                    "status": "succeeded",
                    "artifact_ref": artifact_ref,
                    "manifest_ref": manifest_ref,
                },
            )
        )
        .raise_for_status()
        .json()
    )


def _is_supported_public_github_repo(build: dict, repo_url: str) -> tuple[bool, str]:
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        return False, "fake builder currently supports only public https://github.com repos"

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        return False, "repo URL must include owner and repository name"

    source_repository = build.get("source_snapshot", {}).get("source_repository")
    if source_repository is None:
        source_repository = {}
    if source_repository.get("private") is True:
        return False, "private repositories are not supported in the fake builder flow"

    return True, ""
