from app.builds.repository import BuildRepository
from app.builds.schemas import BuildCreate, BuildTransition
from app.core.exceptions import InvalidTransitionError, NotFoundError

# Allowed state-machine transitions
_BUILD_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "canceled"},
    "running": {"succeeded", "failed", "canceled"},
    "succeeded": set(),  # terminal
    "failed": set(),  # terminal (but can retry via new Build)
    "canceled": set(),  # terminal
}


class BuildService:
    def __init__(self, repo: BuildRepository):
        self._repo = repo

    async def create_build(self, data: BuildCreate) -> dict:
        correlation_id = data.correlation_id or _new_correlation_id()
        # MVP: always start at attempt 1; retry logic can bump this later
        build = await self._repo.create(
            project_id=data.project_id,
            correlation_id=correlation_id,
            attempt=1,
            job_type=data.job_type,
            source_ref=data.source_ref,
            commit_sha=data.commit_sha,
            source_snapshot=data.source_snapshot,
            build_config=data.build_config,
            env_snapshot=data.env_snapshot,
        )
        return self._to_dict(build)

    async def list_builds(self, project_id: str) -> list[dict]:
        builds = await self._repo.list_by_project(project_id)
        return [self._to_dict(b) for b in builds]

    async def get_build(self, build_id: str) -> dict:
        build = await self._repo.get_by_id(build_id)
        if build is None:
            raise NotFoundError("Build", build_id)
        return self._to_dict(build)

    async def transition(self, build_id: str, data: BuildTransition) -> dict:
        build = await self._repo.get_by_id(build_id)
        if build is None:
            raise NotFoundError("Build", build_id)

        allowed = _BUILD_TRANSITIONS.get(build.status, set())
        if data.status not in allowed:
            raise InvalidTransitionError("Build", build.status, data.status)

        fields = {"status": data.status}
        if data.artifact_ref:
            fields["artifact_ref"] = data.artifact_ref
        if data.error_message:
            fields["error_message"] = data.error_message

        build = await self._repo.update(build_id, **fields)
        return self._to_dict(build)

    @staticmethod
    def _to_dict(b) -> dict:
        return {
            "id": b.id,
            "project_id": b.project_id,
            "correlation_id": b.correlation_id,
            "attempt": b.attempt,
            "job_type": getattr(b, "job_type", "build"),
            "status": b.status,
            "source_ref": getattr(b, "source_ref", None),
            "commit_sha": getattr(b, "commit_sha", None),
            "source_snapshot": getattr(b, "source_snapshot", None),
            "build_config": getattr(b, "build_config", None),
            "env_snapshot": getattr(b, "env_snapshot", None),
            "artifact_ref": b.artifact_ref,
            "error_message": b.error_message,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }


def _new_correlation_id() -> str:
    from uuid import uuid4

    return str(uuid4())
