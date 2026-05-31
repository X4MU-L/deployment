from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.background_builder.base import (
    BackgroundBuildDispatchResult,
    BackgroundBuilder,
    BackgroundBuildRequest,
)
from app.cloudflare_builder.contracts import (
    ArtifactTarget,
    BuildRequestedMessage,
    GitCheckoutMetadata,
    StaticBuildSpec,
)
from app.core.config import get_settings


@dataclass(frozen=True)
class CloudflareQueueDispatch:
    queue_name: str
    payload: str
    content_type: str = "application/json"


class CloudflareQueueProducer:
    def publish(self, dispatch: CloudflareQueueDispatch) -> str | None:
        raise RuntimeError(
            "CF_QUEUE_PRODUCER_NOT_CONFIGURED: Cloudflare queue producer is not configured"
        )


class HTTPCloudflareQueueProducer(CloudflareQueueProducer):
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

    def publish(self, dispatch: CloudflareQueueDispatch) -> str | None:
        if not self._account_id or not self._api_token or not self._queue_id:
            raise RuntimeError(
                "CF_QUEUE_PRODUCER_NOT_CONFIGURED: "
                "cloudflare_account_id, cloudflare_api_token, and cloudflare_queue_id are required"
            )

        response = self._get_client().post(
            f"{self._api_base_url}/accounts/{self._account_id}/queues/{self._queue_id}/messages",
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            },
            json={
                "body": json.loads(dispatch.payload),
                "content_type": "json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        # log the full response for debugging, but only return the message ID (job ID) to the caller
        print(f"Cloudflare Queue publish response: {payload}")
        if not payload.get("success", False):
            raise RuntimeError(f"CF_QUEUE_PUSH_FAILED: {payload}")
        return None

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(timeout=10.0)
        return self._client


class CFBuilder(BackgroundBuilder):
    adapter_name = "cloudflare"

    def __init__(self, producer: CloudflareQueueProducer | None = None):
        if producer is not None:
            self._producer = producer
            return
        settings = get_settings()
        self._producer = HTTPCloudflareQueueProducer(
            api_base_url=settings.cloudflare_api_base_url,
            account_id=settings.cloudflare_account_id,
            api_token=settings.cloudflare_api_token,
            queue_id=settings.cloudflare_queue_id,
        )

    def enqueue_build(self, request: BackgroundBuildRequest) -> BackgroundBuildDispatchResult:
        settings = get_settings()
        message = build_build_requested_message(
            request, artifact_bucket=settings.cloudflare_artifact_bucket
        )
        dispatch = CloudflareQueueDispatch(
            queue_name=settings.cloudflare_queue_name,
            payload=message.model_dump_json(by_alias=True),
        )
        job_id = self._producer.publish(dispatch)
        return BackgroundBuildDispatchResult(
            adapter=self.adapter_name,
            job_id=job_id,
        )


def build_build_requested_message(
    request: BackgroundBuildRequest,
    *,
    artifact_bucket: str,
) -> BuildRequestedMessage:
    source_snapshot = request.source_snapshot or {}
    build_config = request.build_config or {}
    artifact_prefix = f"projects/{request.project_id}/releases/{request.planned_release_id}"
    manifest_key = f"{artifact_prefix}/static_release_manifest.v1.json"
    return BuildRequestedMessage(
        build_id=request.build_id,
        project_id=request.project_id,
        environment_id=request.environment_id,
        release_id=request.planned_release_id,
        correlation_id=request.correlation_id,
        attempt=request.attempt,
        git_checkout=GitCheckoutMetadata(
            repo_url=source_snapshot.get("repo_url") or "",
            source_provider=source_snapshot.get("source_provider"),
            repository=source_snapshot.get("source_repository"),
            default_branch=source_snapshot.get("default_branch"),
            source_ref=request.source_ref,
            commit_sha=request.commit_sha,
        ),
        build_spec=StaticBuildSpec(
            root_directory=build_config.get("root_directory"),
            install_command=build_config.get("install_command"),
            build_command=build_config.get("build_command"),
            output_directory=build_config.get("output_directory"),
            framework_preset=build_config.get("framework_preset"),
            package_manager=build_config.get("package_manager"),
            env_snapshot=request.env_snapshot,
        ),
        artifact_target=ArtifactTarget(
            bucket=artifact_bucket,
            prefix=artifact_prefix,
            manifest_key=manifest_key,
        ),
    )
