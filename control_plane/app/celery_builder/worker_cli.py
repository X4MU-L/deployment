from app.celery_builder.celery_app import celery_app
from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=INFO",
            "--pool=solo",
            "-Q",
            settings.celery_builder_queue_name,
        ]
    )
