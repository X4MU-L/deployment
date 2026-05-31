from app.celery_builder.tasks import ProcessBuildTask
from app.core.config import get_settings


class FakeBuilderDispatcher:
    def enqueue_build(self, build_id: str) -> str:
        settings = get_settings()
        async_result = ProcessBuildTask.apply_async(
            build_id=build_id,
            queue=settings.fake_builder_queue_name,
        )
        return str(async_result.id)
