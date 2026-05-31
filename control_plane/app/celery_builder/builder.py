from app.background_builder.base import BackgroundBuildDispatchResult, BackgroundBuilder
from app.celery_builder.tasks import ProcessBuildTask
from app.core.config import get_settings


class CeleryBuilder(BackgroundBuilder):
    """Temporary local-development background builder adapter backed by Celery."""

    adapter_name = "celery"

    def enqueue_build(self, build_id: str) -> BackgroundBuildDispatchResult:
        settings = get_settings()
        async_result = ProcessBuildTask.apply_async(
            build_id=build_id,
            queue=settings.celery_builder_queue_name,
        )
        return BackgroundBuildDispatchResult(
            adapter=self.adapter_name,
            job_id=str(async_result.id),
        )
