from __future__ import annotations

import logging

from app.artifact_store.base import ArtifactStore
from app.artifact_store.local import LocalArtifactStore
from app.artifact_store.r2 import R2ArtifactStore
from app.core.config import Settings

logger = logging.getLogger(__name__)


def build_artifact_store(settings: Settings) -> ArtifactStore:
    logger.info("Initializing artifact store with provider %s", settings.artifact_store_provider)
    provider = settings.artifact_store_provider
    if provider == "local":
        return LocalArtifactStore(settings.artifact_store_root)
    if provider == "r2":
        return R2ArtifactStore(
            endpoint_url=settings.r2_endpoint_url,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            session_token=settings.r2_session_token,
            region_name=settings.r2_region_name,
        )
    raise ValueError(f"Unsupported artifact store provider: {provider}")
