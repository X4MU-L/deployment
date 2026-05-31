from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.artifact_store.r2 import R2ArtifactStore


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        payload = Body.read() if hasattr(Body, "read") else Body
        self.objects[(Bucket, Key)] = payload
        self.content_types[(Bucket, Key)] = ContentType

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


def test_r2_artifact_store_publishes_directory(tmp_path):
    source_dir = tmp_path / "site"
    source_dir.mkdir()
    (source_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    assets_dir = source_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('hi')", encoding="utf-8")

    fake_client: Any = _FakeS3Client()
    store = R2ArtifactStore(client=fake_client)

    uploaded = store.publish_directory(
        bucket="static-artifacts",
        prefix="projects/p1/releases/r1",
        source_dir=source_dir,
    )

    assert uploaded == ["assets/app.js", "index.html"]
    assert (
        fake_client.objects[("static-artifacts", "projects/p1/releases/r1/index.html")]
        == b"<html></html>"
    )
    assert (
        fake_client.objects[("static-artifacts", "projects/p1/releases/r1/assets/app.js")]
        == b"console.log('hi')"
    )
    assert (
        fake_client.content_types[("static-artifacts", "projects/p1/releases/r1/index.html")]
        == "text/html"
    )


def test_r2_artifact_store_json_round_trip():
    fake_client: Any = _FakeS3Client()
    store = R2ArtifactStore(client=fake_client)

    store.write_json(
        bucket="static-artifacts",
        key="projects/p1/releases/r1/manifest.json",
        data={"hello": "world"},
    )
    payload = store.read_json(
        bucket="static-artifacts",
        key="projects/p1/releases/r1/manifest.json",
    )

    assert payload == {"hello": "world"}
    assert (
        fake_client.content_types[("static-artifacts", "projects/p1/releases/r1/manifest.json")]
        == "application/json"
    )


def test_r2_artifact_store_exists_handles_missing_object():
    fake_client: Any = _FakeS3Client()
    store = R2ArtifactStore(client=fake_client)
    assert not store.exists(bucket="static-artifacts", key="missing.json")


def test_r2_artifact_store_requires_config_when_no_client():
    store = R2ArtifactStore()
    with pytest.raises(RuntimeError, match="R2_ARTIFACT_STORE_CONFIG_MISSING"):
        store.exists(bucket="static-artifacts", key="missing.json")
