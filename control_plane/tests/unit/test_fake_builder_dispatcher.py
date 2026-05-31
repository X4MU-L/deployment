from types import SimpleNamespace

import pytest

from app.celery_builder.dispatcher import FakeBuilderDispatcher


def test_enqueue_build_uses_celery_queue(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_apply_async(**kwargs):
        print(f"apply_async called with kwargs={kwargs} and queue={kwargs.get('queue')}")
        captured["build_id"] = kwargs.get("build_id")
        captured["queue"] = kwargs.get("queue")
        return SimpleNamespace(id="job-123")

    monkeypatch.setattr(
        "app.celery_builder.dispatcher.ProcessBuildTask.apply_async",
        _fake_apply_async,
    )
    monkeypatch.setattr(
        "app.celery_builder.dispatcher.get_settings",
        lambda: SimpleNamespace(fake_builder_queue_name="fake-builder"),
    )

    dispatcher = FakeBuilderDispatcher()
    queue_job_id = dispatcher.enqueue_build("build-1")

    assert queue_job_id == "job-123"
    assert captured == {"build_id": "build-1", "queue": "fake-builder"}


def test_enqueue_build_propagates_dispatch_errors(monkeypatch):
    def _fake_apply_async(**kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(
        "app.celery_builder.dispatcher.ProcessBuildTask.apply_async",
        _fake_apply_async,
    )
    monkeypatch.setattr(
        "app.celery_builder.dispatcher.get_settings",
        lambda: SimpleNamespace(fake_builder_queue_name="fake-builder"),
    )

    dispatcher = FakeBuilderDispatcher()
    with pytest.raises(RuntimeError, match="broker down"):
        dispatcher.enqueue_build("build-1")
