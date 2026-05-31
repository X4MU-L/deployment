import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_redis_not_required_for_startup(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", None)

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        r = await ac.get("/api/v1/health")
        assert r.status_code == 200
        assert hasattr(app.state, "redis")
        assert app.state.redis is None


@pytest.mark.asyncio
async def test_configured_redis_client_attached_to_app_state(monkeypatch):
    import redis.asyncio as redis_mod

    class FakeRedis:
        async def aclose(self):
            return None

        async def wait_closed(self):
            return None

    fake_client = FakeRedis()

    def _from_url(*a, **k):
        return fake_client

    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis_mod, "from_url", _from_url)

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        r = await ac.get("/api/v1/health")
        assert r.status_code == 200
        assert hasattr(app.state, "redis")
        assert app.state.redis is fake_client
