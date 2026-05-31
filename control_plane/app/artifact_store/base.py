from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactStoreLocation:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return build_r2_uri(self.bucket, self.key)


def build_r2_uri(bucket: str, key: str) -> str:
    return f"r2://{bucket}/{key}"


def parse_r2_uri(uri: str | None) -> ArtifactStoreLocation:
    if not uri or not uri.startswith("r2://"):
        return ArtifactStoreLocation(bucket="", key="")
    without_scheme = uri.removeprefix("r2://")
    bucket, _, key = without_scheme.partition("/")
    return ArtifactStoreLocation(bucket=bucket, key=key)


class ArtifactStore(ABC):
    adapter_name: str

    @abstractmethod
    def publish_directory(self, *, bucket: str, prefix: str, source_dir: Path) -> list[str]:
        """Publish a directory and return the relative file paths now stored under the prefix."""

    @abstractmethod
    def write_json(self, *, bucket: str, key: str, data: dict[str, Any]) -> None:
        """Write JSON to the given bucket/key."""

    @abstractmethod
    def read_json(self, *, bucket: str, key: str) -> dict[str, Any]:
        """Read JSON from the given bucket/key."""

    @abstractmethod
    def exists(self, *, bucket: str, key: str) -> bool:
        """Return whether the given bucket/key exists."""

    def build_uri(self, *, bucket: str, key: str) -> str:
        return build_r2_uri(bucket, key)

