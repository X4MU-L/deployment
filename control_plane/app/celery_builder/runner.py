from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import httpx

from app.artifact_store import build_artifact_store
from app.core.config import get_settings
from app.static_releases.manifest import (
    STATIC_RELEASE_MANIFEST_SCHEMA,
    build_static_release_manifest,
)


async def run_fake_build(
    client: httpx.AsyncClient,
    *,
    build_id: str,
    service_token: str,
    service_name: str = "fake-builder",
    artifact_bucket: str = "fake-static-artifacts",
    artifact_prefix: str | None = None,
    manifest_key: str | None = None,
    # not included in celery task args
    source_snapshot: dict | None = None,
    build_config: dict | None = None,
    source_ref: str | None = None,
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
    planned_release_id = build["planned_release_id"]
    effective_source_snapshot = source_snapshot or build.get("source_snapshot") or {}
    repo_url = effective_source_snapshot.get("repo_url") or ""
    effective_source_ref = (
        source_ref
        or build.get("source_ref")
        or effective_source_snapshot.get("default_branch")
        or "main"
    )
    effective_build_config = build_config or build.get("build_config") or {}

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
        f"checkout ref: {effective_source_ref}",
    ]
    if supported:
        output_directory = effective_build_config.get("output_directory") or "dist"
        published_artifact = _publish_simulated_static_release(
            project_id=project_id,
            build_id=build_id,
            release_id=planned_release_id,
            project_name=effective_source_snapshot.get("project_name") or build_id,
            output_directory=output_directory,
            bucket=artifact_bucket,
            prefix=artifact_prefix,
            manifest_key=manifest_key,
        )
        log_lines.extend(
            [
                "repo visibility: assumed public",
                "install: simulated dependency install completed",
                "build: simulated static site build completed",
                f"output: simulated static files generated in {output_directory}",
                f"upload: published simulated static release to {published_artifact['artifact_ref']}",  # noqa: E501
                "upload: generated static_release_manifest.v1",
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

    return (
        (
            await client.post(
                f"/api/v1/internal/builds/{build_id}/complete",
                headers=headers,
                json={
                    "status": "succeeded",
                    "artifact_ref": published_artifact["artifact_ref"],
                    "manifest_ref": published_artifact["manifest_ref"],
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


def _publish_simulated_static_release(
    *,
    project_id: str,
    build_id: str,
    release_id: str,
    project_name: str,
    output_directory: str,
    bucket: str,
    prefix: str | None = None,
    manifest_key: str | None = None,
) -> dict[str, str]:
    settings = get_settings()
    store = build_artifact_store(settings)
    artifact_prefix = prefix or f"projects/{project_id}/releases/{release_id}"
    resolved_manifest_key = (
        # "projects/{project_id}/releases/{release_id}/static_release_manifest.v1.json"
        manifest_key or f"{artifact_prefix}/{STATIC_RELEASE_MANIFEST_SCHEMA}.json"
    )

    with TemporaryDirectory(prefix=f"build-{build_id}-") as tmp_dir:
        output_root = Path(tmp_dir) / output_directory
        output_root.mkdir(parents=True, exist_ok=True)
        # possible path  "build-{build_id}-abc123/dist/assets/"
        asset_dir = output_root / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)

        # possible path "build-{build_id}-abc123/dist/index.html"
        index_html = output_root / "index.html"
        index_html.write_text(
            (
                "<!doctype html>\n"
                "<html><head><meta charset='utf-8'><title>"
                f"{project_name}</title></head><body>"
                f"<h1>{project_name}</h1>"
                f"<p>build {build_id}</p>"
                f'<script src="/assets/app-{build_id[:8]}.js"></script>'
                "</body></html>\n"
            ),
            encoding="utf-8",
        )

        # possible path  "build-{build_id}-abc123/dist/assets/app-abc12345.js"
        asset_file = asset_dir / f"app-{build_id[:8]}.js"
        asset_file.write_text(
            f"console.log('build {build_id} for project {project_id}');\n",
            encoding="utf-8",
        )

        # NOTE: The CDN server will need to map the domain http://my-cool-dashboard.local
        # to look directly inside that specific release folder (/.artifacts/.../rel-v1.0.0/),
        # then:The browser requests http://my-cool-dashboard.local -> Server serves index.html.
        # The browser requests /assets/app-abc12345.js -> Server safely finds it at the root of
        # that specific release directory.

        store.publish_directory(bucket=bucket, prefix=artifact_prefix, source_dir=output_root)
        manifest = build_static_release_manifest(
            project_id=project_id,
            release_id=release_id,
            build_id=build_id,
            root_dir=output_root,
            generated_at=datetime.now(UTC),
        )
        store.write_json(bucket=bucket, key=resolved_manifest_key, data=manifest)

    return {
        "artifact_ref": store.build_uri(bucket=bucket, key=artifact_prefix),
        "manifest_ref": store.build_uri(bucket=bucket, key=resolved_manifest_key),
    }
