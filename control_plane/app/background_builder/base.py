from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundBuildDispatchResult:
    adapter: str
    job_id: str | None = None


@dataclass(frozen=True)
class BackgroundBuildRequest:
    build_id: str
    project_id: str
    environment_id: str | None
    correlation_id: str
    attempt: int
    source_ref: str | None
    commit_sha: str | None
    source_snapshot: dict | None
    build_config: dict | None
    env_snapshot: dict | None
    planned_release_id: str


class BackgroundBuilder(ABC):
    adapter_name: str

    @abstractmethod
    def enqueue_build(self, request: BackgroundBuildRequest) -> BackgroundBuildDispatchResult:
        """Schedule background work for the given build."""
