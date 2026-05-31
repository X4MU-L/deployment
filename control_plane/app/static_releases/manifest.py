from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

STATIC_RELEASE_MANIFEST_SCHEMA = "static_release_manifest.v1"
DEFAULT_HTML_MAX_AGE_SECONDS = 30
DEFAULT_ASSET_MAX_AGE_SECONDS = 31536000
DEFAULT_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"


def build_static_release_manifest(
    *,
    project_id: str,
    release_id: str,
    build_id: str,
    root_dir: Path,
    generated_at: datetime | None = None,
    index_document: str = "index.html",
    error_document: str | None = None,
) -> dict:
    generated_at = generated_at or datetime.now(UTC)
    assets = []
    for path in sorted(p for p in root_dir.rglob("*") if p.is_file()):
        relative_path = str(path.relative_to(root_dir)).replace("\\", "/")
        mime_type, _ = mimetypes.guess_type(relative_path)
        assets.append(
            {
                "path": relative_path,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "content_type": mime_type or "application/octet-stream",
            }
        )

    return {
        "schema": STATIC_RELEASE_MANIFEST_SCHEMA,
        "project_id": project_id,
        "release_id": release_id,
        "build_id": build_id,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "index_document": index_document,
        "error_document": error_document,
        "cache_policy": {
            "html_max_age_seconds": DEFAULT_HTML_MAX_AGE_SECONDS,
            "asset_max_age_seconds": DEFAULT_ASSET_MAX_AGE_SECONDS,
            "asset_cache_control": DEFAULT_ASSET_CACHE_CONTROL,
        },
        "assets": assets,
    }
