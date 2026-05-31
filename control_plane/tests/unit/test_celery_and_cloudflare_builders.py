from types import SimpleNamespace

import pytest

from app.celery_builder.builder import CeleryBuilder
from app.cloudflare_builder.builder import CFBuilder


def test_celery_builder_returns_adapter_and_job_id(monkeypatch):
    monkeypatch.setattr(
        "app.celery_builder.builder.get_settings",
        lambda: SimpleNamespace(celery_builder_queue_name="fake-builder"),
    )
    monkeypatch.setattr(
        "app.celery_builder.builder.ProcessBuildTask.apply_async",
        lambda build_id, queue: SimpleNamespace(id="job-123"),
    )

    builder = CeleryBuilder()
    dispatch = builder.enqueue_build("build-1")

    assert dispatch.adapter == "celery"
    assert dispatch.job_id == "job-123"


def test_cloudflare_builder_stub_raises_clear_error():
    builder = CFBuilder()
    with pytest.raises(NotImplementedError, match="CF_BUILDER_NOT_IMPLEMENTED"):
        builder.enqueue_build("build-1")
