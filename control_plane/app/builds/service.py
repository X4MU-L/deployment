from app.audit.service import AuditService
from app.background_builder.base import BackgroundBuilder, BackgroundBuildRequest
from app.builds.repository import BuildRepository
from app.builds.schemas import BuildCreate, BuildTransition, BuildTriggerRequest
from app.core.exceptions import InvalidTransitionError, NotFoundError, ServiceUnavailableError
from app.environments.repository import EnvironmentRepository
from app.projects.repository import ProjectRepository

# Allowed state-machine transitions
_BUILD_TRANSITIONS: dict[str, set[str]] = {
    # Builders may report only a final completion callback for short jobs, so
    # queued builds can move directly to a terminal state without an explicit
    # intermediate "running" update.
    "queued": {"running", "succeeded", "failed", "canceled"},
    "running": {"succeeded", "failed", "canceled"},
    "succeeded": set(),  # terminal
    "failed": set(),  # terminal (but can retry via new Build)
    "canceled": set(),  # terminal
}


class BuildService:
    def __init__(
        self,
        repo: BuildRepository,
        project_repo: ProjectRepository,
        environment_repo: EnvironmentRepository,
        audit: AuditService,
        background_builder: BackgroundBuilder,
    ):
        self._repo = repo
        self._project_repo = project_repo
        self._environment_repo = environment_repo
        self._audit = audit
        self._background_builder = background_builder

    async def create_build(self, data: BuildCreate) -> dict:
        correlation_id = data.correlation_id or _new_correlation_id()
        # MVP: always start at attempt 1; retry logic can bump this later
        build = await self._repo.create(
            project_id=data.project_id,
            environment_id=data.environment_id,
            triggered_by_user_id=data.triggered_by_user_id,
            trigger_source=data.trigger_source,
            correlation_id=correlation_id,
            attempt=1,
            job_type=data.job_type,
            source_ref=data.source_ref,
            commit_sha=data.commit_sha,
            source_snapshot=data.source_snapshot,
            build_config=data.build_config,
            env_snapshot=data.env_snapshot,
            planned_release_id=data.planned_release_id or _new_release_id(),
        )
        return self._to_dict(build)

    async def trigger_build(self, user_id: str, project_id: str, data: BuildTriggerRequest) -> dict:
        project = await self._project_repo.get_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)

        environment = await self._environment_repo.get_by_project_and_name(
            project_id, data.environment_name
        )
        if environment is None:
            raise NotFoundError("Environment", data.environment_name)

        source_snapshot = {
            "project_name": project.name,
            "repo_url": project.repo_url,
            "source_provider": project.source_provider,
            "source_repository": project.source_repository,
            "default_branch": getattr(project, "default_branch", None),
        }

        build = await self.create_build(
            BuildCreate(
                project_id=project.id,
                environment_id=environment.id,
                triggered_by_user_id=user_id,
                trigger_source="user",
                source_ref=data.source_ref or getattr(project, "default_branch", None),
                commit_sha=data.commit_sha,
                source_snapshot=source_snapshot,
                build_config=getattr(project, "build_settings", None),
                env_snapshot=environment.env_vars,
            )
        )
        await self._audit.record(
            actor_type="user",
            actor_user_id=user_id,
            action="build.triggered",
            project_id=project.id,
            build_id=build["id"],
            metadata={"environment_id": environment.id},
        )
        adapter_name = self._background_builder.adapter_name
        try:
            dispatch = self._background_builder.enqueue_build(
                BackgroundBuildRequest(
                    build_id=build["id"],
                    project_id=build["project_id"],
                    environment_id=build["environment_id"],
                    correlation_id=build["correlation_id"],
                    attempt=build["attempt"],
                    source_ref=build["source_ref"],
                    commit_sha=build["commit_sha"],
                    source_snapshot=build["source_snapshot"],
                    build_config=build["build_config"],
                    env_snapshot=build["env_snapshot"],
                    planned_release_id=build["planned_release_id"],
                )
            )
        except Exception as exc:
            # TODO: find a way to make this into a compensating transaction that can be retried,
            # perhaps have a markfailed_build that uses both the create atransaction
            # and the audit log and build update
            await self._repo.update(
                build["id"],
                builder_adapter=adapter_name,
                status="failed",
                error_message=f"Failed to enqueue build via {adapter_name} adapter",
            )
            await self._audit.record(
                actor_type="system",
                action="build.enqueue_failed",
                actor_service=adapter_name,
                project_id=project.id,
                build_id=build["id"],
                metadata={"adapter": adapter_name, "error": str(exc)},
            )
            raise ServiceUnavailableError(
                message=f"Failed to enqueue build via {adapter_name} adapter",
                code="BUILD_DISPATCH_FAILED",
            ) from exc

        # TODO: find a way to make this into a compensating transaction that can be retried,
        # perhaps have a markqueued_build that uses both the create atransaction
        # and the audit log and build update
        updated = await self._repo.update(
            build["id"],
            builder_adapter=dispatch.adapter,
            queue_job_id=dispatch.job_id,
        )
        await self._audit.record(
            actor_type="system",
            action="build.enqueued",
            actor_service=dispatch.adapter,
            project_id=project.id,
            build_id=build["id"],
            metadata={"adapter": dispatch.adapter, "queue_job_id": dispatch.job_id},
        )
        return self._to_dict(updated)

    async def list_builds(self, user_id: str, project_id: str) -> list[dict]:
        project = await self._project_repo.get_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)

        builds = await self._repo.list_by_project_for_user(project_id, user_id)
        return [self._to_dict(b) for b in builds]

    async def get_build_internal(self, build_id: str) -> dict:
        build = await self._repo.get_by_id(build_id)
        if build is None:
            raise NotFoundError("Build", build_id)
        return self._to_dict(build)

    async def get_build(self, user_id: str, build_id: str) -> dict:
        build = await self._repo.get_by_id_for_user(build_id, user_id)
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
            "environment_id": getattr(b, "environment_id", None),
            "triggered_by_user_id": getattr(b, "triggered_by_user_id", None),
            "trigger_source": getattr(b, "trigger_source", "system"),
            "correlation_id": b.correlation_id,
            "attempt": b.attempt,
            "job_type": getattr(b, "job_type", "build"),
            "status": b.status,
            "source_ref": getattr(b, "source_ref", None),
            "commit_sha": getattr(b, "commit_sha", None),
            "source_snapshot": getattr(b, "source_snapshot", None),
            "build_config": getattr(b, "build_config", None),
            "env_snapshot": getattr(b, "env_snapshot", None),
            "planned_release_id": getattr(b, "planned_release_id", None),
            "builder_adapter": getattr(b, "builder_adapter", None),
            "queue_job_id": getattr(b, "queue_job_id", None),
            "artifact_ref": b.artifact_ref,
            "error_message": b.error_message,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }


def _new_correlation_id() -> str:
    from uuid import uuid4

    return str(uuid4())


def _new_release_id() -> str:
    from uuid import uuid4

    return str(uuid4())
