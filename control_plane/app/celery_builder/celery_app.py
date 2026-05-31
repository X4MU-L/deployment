from celery import Celery

from app.core.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "celery_builder",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.celery_builder.tasks"],
    )
    app.conf.update(
        task_default_queue=settings.celery_builder_queue_name,
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=settings.celery_task_eager_propagates,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = create_celery_app()
