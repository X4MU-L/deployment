from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundBuildDispatchResult:
    adapter: str
    job_id: str | None = None


class BackgroundBuilder(ABC):
    adapter_name: str

    @abstractmethod
    def enqueue_build(self, build_id: str) -> BackgroundBuildDispatchResult:
        """Schedule background work for the given build."""
