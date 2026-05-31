from types import SimpleNamespace
from typing import Any

import pytest

from app.background_builder.factory import build_background_builder
from app.celery_builder.builder import CeleryBuilder
from app.cloudflare_builder.builder import CFBuilder


def test_factory_resolves_celery_builder_for_fake_builder_provider():
    settings: Any = SimpleNamespace(background_builder_provider="fake-builder")
    builder = build_background_builder(settings)
    assert isinstance(builder, CeleryBuilder)


def test_factory_resolves_cloudflare_builder_for_cloudflare_provider():
    settings: Any = SimpleNamespace(background_builder_provider="cloudflare")
    builder = build_background_builder(settings)
    assert isinstance(builder, CFBuilder)


def test_factory_rejects_unknown_provider():
    settings: Any = SimpleNamespace(background_builder_provider="bogus")
    with pytest.raises(ValueError, match="Unsupported background builder provider: bogus"):
        build_background_builder(settings)
