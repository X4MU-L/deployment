from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.audit.service import AuditService
from app.background_builder.base import BackgroundBuildDispatchResult
from app.builds.schemas import BuildTriggerRequest
from app.builds.service import BuildService
from app.core.exceptions import ServiceUnavailableError


@pytest.mark.asyncio
async def test_trigger_build_stores_nullable_job_id_for_non_celery_builder():
    repo = SimpleNamespace(
        create=AsyncMock(
            return_value=SimpleNamespace(
                id="build-1",
                project_id="project-1",
                environment_id="env-1",
                triggered_by_user_id="user-1",
                trigger_source="user",
                correlation_id="corr-1",
                attempt=1,
                job_type="build",
                status="queued",
                source_ref="main",
                commit_sha=None,
                source_snapshot={},
                build_config={"build_command": "npm run build"},
                env_snapshot=None,
                builder_adapter=None,
                queue_job_id=None,
                artifact_ref=None,
                error_message=None,
                created_at=None,
                updated_at=None,
            )
        ),
        update=AsyncMock(
            return_value=SimpleNamespace(
                id="build-1",
                project_id="project-1",
                environment_id="env-1",
                triggered_by_user_id="user-1",
                trigger_source="user",
                correlation_id="corr-1",
                attempt=1,
                job_type="build",
                status="queued",
                source_ref="main",
                commit_sha=None,
                source_snapshot={},
                build_config={"build_command": "npm run build"},
                env_snapshot=None,
                builder_adapter="cloudflare",
                queue_job_id=None,
                artifact_ref=None,
                error_message=None,
                created_at=None,
                updated_at=None,
            )
        ),
    )
    project_repo = SimpleNamespace(
        get_by_id_for_user=AsyncMock(
            return_value=SimpleNamespace(
                id="project-1",
                name="demo",
                repo_url="https://github.com/example/demo",
                source_provider="github",
                source_repository={"full_name": "example/demo", "private": False},
                default_branch="main",
                build_settings={"build_command": "npm run build"},
            )
        )
    )
    environment_repo = SimpleNamespace(
        get_by_project_and_name=AsyncMock(
            return_value=SimpleNamespace(id="env-1", env_vars=None)
        )
    )
    audit = SimpleNamespace(record=AsyncMock(spec=AuditService.record))
    background_builder = SimpleNamespace(
        adapter_name="cloudflare",
        enqueue_build=lambda build_id: BackgroundBuildDispatchResult(adapter="cloudflare", job_id=None),
    )

    service = BuildService(repo, project_repo, environment_repo, audit, background_builder)

    build = await service.trigger_build("user-1", "project-1", BuildTriggerRequest())

    assert build["builder_adapter"] == "cloudflare"
    assert build["queue_job_id"] is None
    repo.update.assert_awaited_with(
        "build-1",
        builder_adapter="cloudflare",
        queue_job_id=None,
    )


@pytest.mark.asyncio
async def test_trigger_build_marks_failed_when_background_enqueue_errors():
    repo = SimpleNamespace(
        create=AsyncMock(
            return_value=SimpleNamespace(
                id="build-1",
                project_id="project-1",
                environment_id="env-1",
                triggered_by_user_id="user-1",
                trigger_source="user",
                correlation_id="corr-1",
                attempt=1,
                job_type="build",
                status="queued",
                source_ref="main",
                commit_sha=None,
                source_snapshot={},
                build_config=None,
                env_snapshot=None,
                builder_adapter=None,
                queue_job_id=None,
                artifact_ref=None,
                error_message=None,
                created_at=None,
                updated_at=None,
            )
        ),
        update=AsyncMock(),
    )
    project_repo = SimpleNamespace(
        get_by_id_for_user=AsyncMock(
            return_value=SimpleNamespace(
                id="project-1",
                name="demo",
                repo_url="https://github.com/example/demo",
                source_provider="github",
                source_repository={"full_name": "example/demo", "private": False},
                default_branch="main",
                build_settings=None,
            )
        )
    )
    environment_repo = SimpleNamespace(
        get_by_project_and_name=AsyncMock(
            return_value=SimpleNamespace(id="env-1", env_vars=None)
        )
    )
    audit = SimpleNamespace(record=AsyncMock(spec=AuditService.record))

    class _FailingBuilder:
        adapter_name = "cloudflare"

        def enqueue_build(self, build_id: str):
            raise NotImplementedError(
                "CF_BUILDER_NOT_IMPLEMENTED: Cloudflare builder adapter is not implemented yet"
            )

    service = BuildService(repo, project_repo, environment_repo, audit, _FailingBuilder())

    with pytest.raises(ServiceUnavailableError) as exc:
        await service.trigger_build("user-1", "project-1", BuildTriggerRequest())

    assert exc.value.code == "BUILD_DISPATCH_FAILED"
    repo.update.assert_awaited_with(
        "build-1",
        builder_adapter="cloudflare",
        status="failed",
        error_message="Failed to enqueue build via cloudflare adapter",
    )
