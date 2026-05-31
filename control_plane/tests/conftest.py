import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.dependencies import get_db
from app.db.models import *  # noqa: F403
from app.db.models.base import Base
from app.main import app

# File-backed SQLite for tests
TEST_DB_URL = "sqlite+aiosqlite:///./control_plane_test.db"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionFactory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def local_artifact_store_root(tmp_path, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(settings, "artifact_store_root", str(artifact_root))
    monkeypatch.setattr(settings, "artifact_store_provider", "local")
    return artifact_root


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Client with a registered + logged-in user."""
    reg = await client.post(
        "/api/v1/auth/register/password",
        json={"email": "test@example.com", "password": "secret123"},
    )
    assert reg.status_code == 201
    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "test@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
