from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.artifact_store.base import ArtifactStore


class LocalArtifactStore(ArtifactStore):
    """Local filesystem artifact store that mimics bucket/key addressing."""

    adapter_name = "local"

    def __init__(self, root: str | Path):
        self._root = Path(root)

    def publish_directory(self, *, bucket: str, prefix: str, source_dir: Path) -> list[str]:
        target_root = self._root / bucket / prefix
        if target_root.exists():
            shutil.rmtree(target_root)
        shutil.copytree(source_dir, target_root)
        return sorted(
            str(path.relative_to(target_root)).replace("\\", "/")
            for path in target_root.rglob("*")
            if path.is_file()
        )

    def write_json(self, *, bucket: str, key: str, data: dict[str, Any]) -> None:
        target = self._root / bucket / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def read_json(self, *, bucket: str, key: str) -> dict[str, Any]:
        target = self._root / bucket / key
        return json.loads(target.read_text(encoding="utf-8"))

    def exists(self, *, bucket: str, key: str) -> bool:
        return (self._root / bucket / key).exists()
