from types import SimpleNamespace

import pytest

from app.background_builder.factory import build_background_builder
from app.celery_builder.builder import CeleryBuilder
from app.cloudflare_builder.builder import CFBuilder


def test_factory_resolves_celery_builder_for_fake_builder_provider():
    builder = build_background_builder(SimpleNamespace(background_builder_provider="fake-builder"))
    assert isinstance(builder, CeleryBuilder)


def test_factory_resolves_cloudflare_builder_for_cloudflare_provider():
    builder = build_background_builder(SimpleNamespace(background_builder_provider="cloudflare"))
    assert isinstance(builder, CFBuilder)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported background builder provider: bogus"):
        build_background_builder(SimpleNamespace(background_builder_provider="bogus"))
