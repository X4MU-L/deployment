import hashlib
import json
from pathlib import Path

from app.artifact_store.local import LocalArtifactStore
from app.static_releases.manifest import (
    STATIC_RELEASE_MANIFEST_SCHEMA,
    build_static_release_manifest,
)


def test_build_static_release_manifest_from_directory(tmp_path):
    root = tmp_path / "dist"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text("<html>Hello</html>\n", encoding="utf-8")
    js_content = "console.log('hello');\n"
    (assets / "app.js").write_text(js_content, encoding="utf-8")

    manifest = build_static_release_manifest(
        project_id="project-1",
        release_id="release-1",
        build_id="build-1",
        root_dir=root,
    )

    assert manifest["schema"] == STATIC_RELEASE_MANIFEST_SCHEMA
    assert manifest["project_id"] == "project-1"
    assert manifest["release_id"] == "release-1"
    assert manifest["build_id"] == "build-1"
    assert manifest["index_document"] == "index.html"
    assert [asset["path"] for asset in manifest["assets"]] == ["assets/app.js", "index.html"]
    js_asset = next(asset for asset in manifest["assets"] if asset["path"] == "assets/app.js")
    assert js_asset["sha256"] == hashlib.sha256(js_content.encode("utf-8")).hexdigest()
    assert js_asset["content_type"] == "text/javascript"


def test_local_artifact_store_round_trips_json(tmp_path):
    store = LocalArtifactStore(tmp_path)
    store.write_json(bucket="artifacts", key="projects/p1/manifest.json", data={"hello": "world"})
    payload = store.read_json(bucket="artifacts", key="projects/p1/manifest.json")
    assert payload == {"hello": "world"}

    target = tmp_path / "artifacts" / "projects" / "p1" / "manifest.json"
    assert json.loads(target.read_text(encoding="utf-8")) == {"hello": "world"}
