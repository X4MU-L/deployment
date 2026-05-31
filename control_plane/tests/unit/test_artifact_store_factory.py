from types import SimpleNamespace
from typing import Any

import pytest

from app.artifact_store.base import build_r2_uri, parse_r2_uri
from app.artifact_store.factory import build_artifact_store
from app.artifact_store.local import LocalArtifactStore
from app.artifact_store.r2 import R2ArtifactStore


def test_factory_resolves_local_artifact_store():
    settings: Any = SimpleNamespace(
        artifact_store_provider="local", artifact_store_root="/tmp/artifacts"
    )
    store = build_artifact_store(settings)
    assert isinstance(store, LocalArtifactStore)


def test_factory_resolves_r2_artifact_store():
    settings: Any = SimpleNamespace(
        artifact_store_provider="r2",
        artifact_store_root="/tmp/artifacts",
        r2_endpoint_url="https://example.r2.cloudflarestorage.com",
        r2_access_key_id="access-key",
        r2_secret_access_key="secret-key",
        r2_session_token=None,
        r2_region_name="auto",
    )
    store = build_artifact_store(settings)
    assert isinstance(store, R2ArtifactStore)


def test_factory_rejects_unknown_provider():
    settings: Any = SimpleNamespace(
        artifact_store_provider="bogus",
        artifact_store_root="/tmp/artifacts",
        r2_endpoint_url="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_session_token=None,
        r2_region_name="auto",
    )
    with pytest.raises(ValueError, match="Unsupported artifact store provider: bogus"):
        build_artifact_store(settings)


def test_r2_uri_helpers_round_trip():
    uri = build_r2_uri("artifacts", "projects/p1/releases/r1/manifest.json")
    parsed = parse_r2_uri(uri)

    assert uri == "r2://artifacts/projects/p1/releases/r1/manifest.json"
    assert parsed.bucket == "artifacts"
    assert parsed.key == "projects/p1/releases/r1/manifest.json"


def test_r2_stub_raises_clear_error():
    store = R2ArtifactStore()
    with pytest.raises(RuntimeError, match="R2_ARTIFACT_STORE_CONFIG_MISSING"):
        store.exists(bucket="artifacts", key="projects/p1/releases/r1/manifest.json")
