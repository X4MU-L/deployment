from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.artifact_store.base import ArtifactStore


class R2ArtifactStore(ArtifactStore):
    adapter_name = "r2"

    def __init__(
        self,
        *,
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        session_token: str | None = None,
        region_name: str = "auto",
        client: BaseClient | None = None,
    ):
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._session_token = session_token
        self._region_name = region_name
        self._client = client

    def publish_directory(self, *, bucket: str, prefix: str, source_dir: Path) -> list[str]:

        uploaded_paths: list[str] = []
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative_path = str(path.relative_to(source_dir)).replace("\\", "/")
            key = _join_key(prefix, relative_path)
            content_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
            with path.open("rb") as file_obj:
                self._get_client().put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=file_obj,
                    ContentType=content_type,
                )
            uploaded_paths.append(relative_path)
        return uploaded_paths

    def write_json(self, *, bucket: str, key: str, data: dict[str, Any]) -> None:
        self._get_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )

    def read_json(self, *, bucket: str, key: str) -> dict[str, Any]:
        response = self._get_client().get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))

    def exists(self, *, bucket: str, key: str) -> bool:
        try:
            self._get_client().head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def _get_client(self) -> BaseClient:
        if self._client is not None:
            return self._client
        if not self._endpoint_url or not self._access_key_id or not self._secret_access_key:
            raise RuntimeError(
                "R2_ARTIFACT_STORE_CONFIG_MISSING: "
                "r2_endpoint_url, r2_access_key_id, and r2_secret_access_key are required"
            )
        self._client = boto3.client(
            service_name="s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            aws_session_token=self._session_token,
            region_name=self._region_name,
            config=Config(signature_version="s3v4"),
        )
        return self._client


def _join_key(prefix: str, relative_path: str) -> str:
    normalized_prefix = prefix.rstrip("/")
    normalized_path = relative_path.lstrip("/")
    if not normalized_prefix:
        return normalized_path
    if not normalized_path:
        return normalized_prefix
    return f"{normalized_prefix}/{normalized_path}"
