from types import SimpleNamespace

import httpx
import pytest

from app.background_builder.base import BackgroundBuildRequest
from app.celery_builder.builder import CeleryBuilder
from app.cloudflare_builder.builder import (
    CFBuilder,
    CloudflareQueueDispatch,
    HTTPCloudflareQueueProducer,
    build_build_requested_message,
)


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
    dispatch = builder.enqueue_build(
        BackgroundBuildRequest(
            build_id="build-1",
            project_id="project-1",
            environment_id="env-1",
            correlation_id="corr-1",
            attempt=1,
            source_ref="refs/heads/main",
            commit_sha=None,
            source_snapshot={},
            build_config={},
            env_snapshot=None,
            planned_release_id="release-1",
        )
    )

    assert dispatch.adapter == "celery"
    assert dispatch.job_id == "job-123"


def test_cloudflare_builder_builds_build_requested_v1_payload(monkeypatch):
    dispatched: list[CloudflareQueueDispatch] = []

    class _Producer:
        def publish(self, dispatch: CloudflareQueueDispatch) -> str | None:
            dispatched.append(dispatch)
            return "cf-job-1"

    monkeypatch.setattr(
        "app.cloudflare_builder.builder.get_settings",
        lambda: SimpleNamespace(
            cloudflare_queue_name="build-requested",
            cloudflare_artifact_bucket="static-artifacts",
        ),
    )
    builder = CFBuilder(producer=_Producer())

    dispatch = builder.enqueue_build(
        BackgroundBuildRequest(
            build_id="build-1",
            project_id="project-1",
            environment_id="env-1",
            correlation_id="corr-1",
            attempt=1,
            source_ref="refs/heads/main",
            commit_sha="abc123",
            source_snapshot={
                "repo_url": "https://github.com/example/demo",
                "source_provider": "github",
                "source_repository": {"full_name": "example/demo", "private": False},
                "default_branch": "main",
            },
            build_config={
                "install_command": "npm install",
                "build_command": "npm run build",
                "output_directory": "dist",
            },
            env_snapshot={"NODE_ENV": "production"},
            planned_release_id="release-1",
        )
    )

    assert dispatch.adapter == "cloudflare"
    assert dispatch.job_id == "cf-job-1"
    assert len(dispatched) == 1
    payload = dispatched[0].payload
    assert '"schema":"build.requested.v1"' in payload
    assert '"release_id":"release-1"' in payload
    assert '"bucket":"static-artifacts"' in payload
    assert '"prefix":"projects/project-1/releases/release-1"' in payload


def test_build_requested_message_uses_release_target_prefix():
    message = build_build_requested_message(
        BackgroundBuildRequest(
            build_id="build-1",
            project_id="project-1",
            environment_id="env-1",
            correlation_id="corr-1",
            attempt=1,
            source_ref="refs/heads/main",
            commit_sha=None,
            source_snapshot={"repo_url": "https://github.com/example/demo"},
            build_config={"output_directory": "dist"},
            env_snapshot=None,
            planned_release_id="release-1",
        ),
        artifact_bucket="static-artifacts",
    )

    assert message.release_id == "release-1"
    assert message.artifact_target.prefix == "projects/project-1/releases/release-1"
    assert (
        message.artifact_target.manifest_key
        == "projects/project-1/releases/release-1/static_release_manifest.v1.json"
    )


def test_http_cloudflare_queue_producer_posts_json_message():
    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "metadata": {
                        "metrics": {
                            "backlog_bytes": 128,
                            "backlog_count": 1,
                            "oldest_message_timestamp_ms": 1710950954154,
                        }
                    }
                },
            },
        )

    producer = HTTPCloudflareQueueProducer(
        api_base_url="https://api.cloudflare.com/client/v4",
        account_id="acct-1",
        api_token="token-1",
        queue_id="queue-1",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    job_id = producer.publish(
        CloudflareQueueDispatch(
            queue_name="build-requested",
            payload='{"schema":"build.requested.v1","build_id":"build-1"}',
        )
    )

    assert job_id is None
    assert captured["url"] == "https://api.cloudflare.com/client/v4/accounts/acct-1/queues/queue-1/messages"
    assert captured["auth"] == "Bearer token-1"
    assert captured["content_type"] == "application/json"
    assert '"content_type":"json"' in captured["body"]
    assert '"schema":"build.requested.v1"' in captured["body"]


def test_http_cloudflare_queue_producer_requires_config():
    producer = HTTPCloudflareQueueProducer(
        api_base_url="https://api.cloudflare.com/client/v4",
        account_id="",
        api_token="",
        queue_id="",
    )
    with pytest.raises(RuntimeError, match="CF_QUEUE_PRODUCER_NOT_CONFIGURED"):
        producer.publish(CloudflareQueueDispatch(queue_name="build-requested", payload="{}"))


def test_cloudflare_builder_without_config_raises_clear_error():
    builder = CFBuilder()
    with pytest.raises(RuntimeError, match="CF_QUEUE_PRODUCER_NOT_CONFIGURED"):
        builder.enqueue_build(
            BackgroundBuildRequest(
                build_id="build-1",
                project_id="project-1",
                environment_id="env-1",
                correlation_id="corr-1",
                attempt=1,
                source_ref=None,
                commit_sha=None,
                source_snapshot={"repo_url": "https://github.com/example/demo"},
                build_config=None,
                env_snapshot=None,
                planned_release_id="release-1",
            )
        )
