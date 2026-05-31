from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.cloudflare_builder.pull_consumer import (
    CloudflarePullConsumer,
    CloudflareQueueClient,
    FakeBuildMessageHandler,
    PulledMessage,
)


def test_pulled_message_decodes_base64_json():
    payload = {"schema": "build.requested.v1", "build_id": "build-1"}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    message = PulledMessage(
        body=encoded,
        id="msg-1",
        timestamp_ms=1710950954154,
        attempts=1,
        lease_id="lease-1",
        metadata={"CF-Content-Type": "json"},
    )

    assert message.decode_body() == payload


def test_queue_client_pulls_and_acks_messages():
    captured = {"pull": None, "ack": None}

    def _handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        if request.url.path.endswith("/messages/pull"):
            captured["pull"] = body
            payload = base64.b64encode(
                json.dumps({"schema": "build.requested.v1", "build_id": "build-1"}).encode("utf-8")
            ).decode("utf-8")
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "messages": [
                            {
                                "body": payload,
                                "id": "msg-1",
                                "timestamp_ms": 1710950954154,
                                "attempts": 1,
                                "metadata": {"CF-Content-Type": "json"},
                                "lease_id": "lease-1",
                            }
                        ]
                    },
                },
            )
        captured["ack"] = body
        return httpx.Response(200, json={"success": True, "result": {"ackCount": 1, "retryCount": 0}})

    client = CloudflareQueueClient(
        api_base_url="https://api.cloudflare.com/client/v4",
        account_id="acct-1",
        api_token="token-1",
        queue_id="queue-1",
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
    )

    messages = client.pull_messages(batch_size=2, visibility_timeout_ms=6000)
    assert len(messages) == 1
    assert messages[0].lease_id == "lease-1"

    client.acknowledge(acks=["lease-1"], retries=[])
    assert captured["pull"] == {"batch_size": 2, "visibility_timeout_ms": 6000}
    assert captured["ack"] == {"acks": [{"lease_id": "lease-1"}], "retries": []}


def test_pull_consumer_acks_success_and_retries_failures():
    payload = {
        "schema": "build.requested.v1",
        "build_id": "build-1",
        "project_id": "project-1",
        "environment_id": "env-1",
        "release_id": "release-1",
        "correlation_id": "corr-1",
        "attempt": 1,
        "git_checkout": {"repo_url": "https://github.com/example/demo"},
        "build_spec": {"kind": "static"},
        "artifact_target": {
            "provider": "r2",
            "bucket": "static-artifacts",
            "prefix": "projects/project-1/releases/release-1",
            "manifest_key": "projects/project-1/releases/release-1/static_release_manifest.v1.json",
        },
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    first = PulledMessage(
        body=encoded,
        id="msg-1",
        timestamp_ms=1710950954154,
        attempts=1,
        lease_id="lease-ok",
        metadata={"CF-Content-Type": "json"},
    )
    second = PulledMessage(
        body="!!!bad!!!",
        id="msg-2",
        timestamp_ms=1710950954155,
        attempts=1,
        lease_id="lease-retry",
        metadata={"CF-Content-Type": "json"},
    )

    class _QueueClient:
        def __init__(self):
            self.acks = None

        def pull_messages(self, *, batch_size: int, visibility_timeout_ms: int):
            return [first, second]

        def acknowledge(self, *, acks: list[str], retries: list[str]):
            self.acks = {"acks": acks, "retries": retries}
            return {"success": True}

    class _Handler:
        def __init__(self):
            self.handled = []

        def handle(self, message):
            self.handled.append(message.build_id)
            return {"ok": True}

    queue_client = _QueueClient()
    handler = _Handler()
    consumer = CloudflarePullConsumer(
        queue_client=queue_client,
        handler=handler,
        batch_size=5,
        visibility_timeout_ms=30000,
    )

    processed = consumer.run_once()

    assert processed == 2
    assert handler.handled == ["build-1"]
    assert queue_client.acks == {"acks": ["lease-ok"], "retries": ["lease-retry"]}


def test_fake_build_message_handler_uses_message_artifact_target(monkeypatch):
    captured = {}

    async def _fake_run_fake_build_task(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        "app.cloudflare_builder.pull_consumer.run_fake_build_task",
        _fake_run_fake_build_task,
    )

    payload = type(
        "Message",
        (),
        {
            "build_id": "build-1",
            "git_checkout": type(
                "GitCheckout",
                (),
                {
                    "repo_url": "https://github.com/example/demo",
                    "source_provider": "github",
                    "repository": {"full_name": "example/demo", "private": False},
                    "default_branch": "main",
                    "source_ref": "refs/heads/release",
                },
            )(),
            "build_spec": type(
                "BuildSpec",
                (),
                {
                    "root_directory": None,
                    "install_command": "npm install",
                    "build_command": "npm run build",
                    "output_directory": "public-dist",
                    "framework_preset": "vite",
                    "package_manager": "npm",
                },
            )(),
            "artifact_target": type(
                "ArtifactTarget",
                (),
                {
                    "bucket": "static-artifacts",
                    "prefix": "projects/project-1/releases/release-1",
                    "manifest_key": (
                        "projects/project-1/releases/release-1/"
                        "static_release_manifest.v1.json"
                    ),
                },
            )(),
        },
    )()
    handler = FakeBuildMessageHandler(
        base_url="http://localhost:8000",
        service_token="token-1",
        service_name="fake-builder",
    )

    result = handler.handle(payload)

    assert result == {"ok": True}
    assert captured["artifact_bucket"] == "static-artifacts"
    assert captured["artifact_prefix"] == "projects/project-1/releases/release-1"
    assert (
        captured["manifest_key"]
        == "projects/project-1/releases/release-1/static_release_manifest.v1.json"
    )
    assert captured["source_snapshot"] == {
        "repo_url": "https://github.com/example/demo",
        "source_provider": "github",
        "source_repository": {"full_name": "example/demo", "private": False},
        "default_branch": "main",
    }
    assert captured["build_config"] == {
        "root_directory": None,
        "install_command": "npm install",
        "build_command": "npm run build",
        "output_directory": "public-dist",
        "framework_preset": "vite",
        "package_manager": "npm",
    }
    assert captured["source_ref"] == "refs/heads/release"
    assert captured["build_id"] == "build-1"
