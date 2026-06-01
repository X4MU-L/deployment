from __future__ import annotations

import argparse
import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.celery_builder.execution import run_fake_build_task
from app.celery_builder.tasks import _run_async
from app.cloudflare_builder.contracts import BuildRequestedMessage
from app.core.config import get_settings


@dataclass(frozen=True)
class PulledMessage:
    body: str
    id: str
    timestamp_ms: int
    attempts: int
    lease_id: str
    metadata: dict[str, Any] | None = None

    @property
    def content_type(self) -> str:
        metadata = self.metadata or {}
        return str(metadata.get("CF-Content-Type") or "json")

    def decode_body(self) -> Any:
        if self.content_type == "text":
            return self.body
        decoded = base64.b64decode(self.body)
        if self.content_type == "json":
            return json.loads(decoded.decode("utf-8"))
        if self.content_type == "bytes":
            return decoded
        raise ValueError(f"Unsupported queue content type: {self.content_type}")


class QueueMessageHandler(Protocol):
    def handle(self, message: BuildRequestedMessage) -> dict[str, Any]: ...


class CloudflareQueueClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        account_id: str,
        api_token: str,
        queue_id: str,
        client: httpx.Client | None = None,
    ):
        self._api_base_url = api_base_url.rstrip("/")
        self._account_id = account_id
        self._api_token = api_token
        self._queue_id = queue_id
        self._client = client

    def pull_messages(
        self,
        *,
        batch_size: int,
        visibility_timeout_ms: int,
    ) -> list[PulledMessage]:
        response = self._request(
            "messages/pull",
            {
                "batch_size": batch_size,
                "visibility_timeout_ms": visibility_timeout_ms,
            },
        )
        result = response.get("result") or {}
        messages = result.get("messages") or []
        return [
            PulledMessage(
                body=str(item["body"]),
                id=str(item["id"]),
                timestamp_ms=int(item["timestamp_ms"]),
                attempts=int(item["attempts"]),
                lease_id=str(item["lease_id"]),
                metadata=item.get("metadata"),
            )
            for item in messages
        ]

    def acknowledge(self, *, acks: list[str], retries: list[str]) -> dict[str, Any]:
        return self._request(
            "messages/ack",
            {
                "acks": [{"lease_id": lease_id} for lease_id in acks],
                "retries": [{"lease_id": lease_id} for lease_id in retries],
            },
        )

    def _request(self, suffix: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._account_id or not self._api_token or not self._queue_id:
            raise RuntimeError(
                "CF_QUEUE_PULL_NOT_CONFIGURED: "
                "cloudflare_account_id, cloudflare_api_token, and cloudflare_queue_id are required"
            )

        response = self._get_client().post(
            f"{self._api_base_url}/accounts/{self._account_id}/queues/{self._queue_id}/{suffix}",
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        parsed = response.json()
        if not parsed.get("success", False):
            raise RuntimeError(f"CF_QUEUE_REQUEST_FAILED: {parsed}")
        return parsed

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(timeout=15.0)
        return self._client


class FakeBuildMessageHandler:
    def __init__(self, *, base_url: str, service_token: str, service_name: str):
        self._base_url = base_url
        self._service_token = service_token
        self._service_name = service_name

    def handle(self, message: BuildRequestedMessage) -> dict[str, Any]:
        return _run_async(
            run_fake_build_task(
                build_id=message.build_id,
                base_url=self._base_url,
                service_token=self._service_token,
                service_name=self._service_name,
                artifact_bucket=message.artifact_target.bucket,
                artifact_prefix=message.artifact_target.prefix,
                manifest_key=message.artifact_target.manifest_key,
                source_snapshot={
                    "repo_url": message.git_checkout.repo_url,
                    "source_provider": message.git_checkout.source_provider,
                    "source_repository": message.git_checkout.repository,
                    "default_branch": message.git_checkout.default_branch,
                },
                build_config={
                    "root_directory": message.build_spec.root_directory,
                    "install_command": message.build_spec.install_command,
                    "build_command": message.build_spec.build_command,
                    "output_directory": message.build_spec.output_directory,
                    "framework_preset": message.build_spec.framework_preset,
                    "package_manager": message.build_spec.package_manager,
                },
                source_ref=message.git_checkout.source_ref,
            )
        )


class CloudflarePullConsumer:
    def __init__(
        self,
        *,
        queue_client: CloudflareQueueClient,
        handler: QueueMessageHandler,
        batch_size: int,
        visibility_timeout_ms: int,
    ):
        self._queue_client = queue_client
        self._handler = handler
        self._batch_size = batch_size
        self._visibility_timeout_ms = visibility_timeout_ms

    def run_once(self) -> int:
        messages = self._queue_client.pull_messages(
            batch_size=self._batch_size,
            visibility_timeout_ms=self._visibility_timeout_ms,
        )
        if not messages:
            return 0

        acks: list[str] = []
        retries: list[str] = []
        for message in messages:
            try:
                decoded = message.decode_body()
                build_request = BuildRequestedMessage.model_validate(decoded)
                self._handler.handle(build_request)
            except Exception:
                retries.append(message.lease_id)
            else:
                acks.append(message.lease_id)

        self._queue_client.acknowledge(acks=acks, retries=retries)
        return len(messages)


def build_pull_consumer() -> CloudflarePullConsumer:
    settings = get_settings()
    queue_client = CloudflareQueueClient(
        api_base_url=settings.cloudflare_api_base_url,
        account_id=settings.cloudflare_account_id,
        api_token=settings.cloudflare_api_token,
        queue_id=settings.cloudflare_queue_id,
    )
    handler = FakeBuildMessageHandler(
        base_url=settings.celery_builder_base_url,
        service_token=settings.internal_service_token,
        service_name=settings.celery_builder_service_name,
    )
    return CloudflarePullConsumer(
        queue_client=queue_client,
        handler=handler,
        batch_size=settings.cloudflare_pull_batch_size,
        visibility_timeout_ms=settings.cloudflare_pull_visibility_timeout_ms,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Cloudflare pull-based builder worker")
    parser.add_argument("--once", action="store_true", help="Process one pull cycle and exit")
    args = parser.parse_args()

    settings = get_settings()
    consumer = build_pull_consumer()
    if args.once:
        consumer.run_once()
        return

    while True:
        processed = consumer.run_once()
        if processed == 0:
            time.sleep(settings.cloudflare_pull_poll_interval_seconds)
