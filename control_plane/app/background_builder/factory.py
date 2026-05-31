from __future__ import annotations

from app.background_builder.base import BackgroundBuilder
from app.celery_builder.builder import CeleryBuilder
from app.cloudflare_builder.builder import CFBuilder
from app.core.config import Settings


def build_background_builder(settings: Settings) -> BackgroundBuilder:
    provider = settings.background_builder_provider
    if provider in {"fake-builder", "celery"}:
        return CeleryBuilder()
    if provider == "cloudflare":
        return CFBuilder()
    raise ValueError(f"Unsupported background builder provider: {provider}")
