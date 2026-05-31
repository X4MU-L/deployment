import pytest

from app.celery_builder.runner import _is_supported_public_github_repo
from app.celery_builder.tasks import _process_build_task, _run_async


def test_supported_public_github_repo():
    supported, reason = _is_supported_public_github_repo(
        {"source_snapshot": {"source_repository": {"private": False}}},
        "https://github.com/example/repo",
    )
    assert supported is True
    assert reason == ""


def test_private_repo_is_rejected():
    supported, reason = _is_supported_public_github_repo(
        {"source_snapshot": {"source_repository": {"private": True}}},
        "https://github.com/example/private-repo",
    )
    assert supported is False
    assert "private repositories" in reason


def test_non_https_repo_is_rejected():
    supported, reason = _is_supported_public_github_repo(
        {"source_snapshot": {"source_repository": {"private": False}}},
        "git@github.com:example/repo.git",
    )
    assert supported is False
    assert "https://github.com" in reason


def test_run_async_executes_coro_without_running_loop():
    async def _sample():
        return "ok"

    assert _run_async(_sample()) == "ok"


@pytest.mark.asyncio
async def test_run_async_executes_when_loop_is_already_running():
    async def _sample():
        return "ok"

    assert _run_async(_sample()) == "ok"


def test_process_build_task_uses_current_settings(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_run_fake_build_task(**kwargs):
        captured.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr("app.celery_builder.tasks._run_fake_build_task", _fake_run_fake_build_task)
    monkeypatch.setattr(
        "app.celery_builder.tasks.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "internal_service_token": "svc-token",
                "celery_builder_service_name": "fake-builder",
                "celery_builder_artifact_bucket": "bucket",
                "celery_builder_base_url": "http://cp.internal",
            },
        )(),
    )

    result = _process_build_task.run("build-123")
    assert result == {"status": "ok"}
    assert captured == {
        "build_id": "build-123",
        "base_url": "http://cp.internal",
        "service_token": "svc-token",
        "service_name": "fake-builder",
        "artifact_bucket": "bucket",
        "artifact_prefix": None,
        "manifest_key": None,
    }
