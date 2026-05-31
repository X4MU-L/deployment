from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.db import models as _models  # noqa: F401
from app.db.models.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = None
    if settings.REDIS_URL:
        try:
            app.state.redis = redis.from_url(settings.REDIS_URL)
        except Exception:
            print(
                "Warning: Failed to create Redis client at startup. "
                "Redis-dependent features will not work."
            )
            app.state.redis = None

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

    # Gracefully close redis client created at startup
    try:
        client = getattr(app.state, "redis", None)
        if client is not None:
            await client.aclose()
            await client.wait_closed()
    except Exception:
        pass


app = FastAPI(title="Deployment Control Plane", version="0.1.0", lifespan=lifespan)
app.include_router(v1_router)
