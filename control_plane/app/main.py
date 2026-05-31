import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.logging import LoggingMiddleware, setup_logging
from app.core.span_attributes_middleware import SpanAttributesMiddleware
from app.core.tracing import instrument_fastapi_app
from app.db import models as _models  # noqa: F401
from app.db.models.base import Base
from app.db.session import engine

settings = get_settings()
logger = logging.getLogger(settings.logger_name)


@asynccontextmanager
async def lifespan(app: FastAPI):

    # 1. Logging must be set up first so all startup events are captured.
    setup_logging(level=settings.log_level, name=settings.logger_name)

    # ── OpenTelemetry: Instrument FastAPI app early (before middleware) ───────────
    instrument_fastapi_app(app)

    app.state.redis = None
    if settings.REDIS_URL:
        try:
            app.state.redis = redis.from_url(settings.REDIS_URL)
            logger.info("Successfully connected to Redis at startup.")
        except Exception:
            logger.warning(
                "Warning: Failed to create Redis client at startup. "
                "Redis-dependent features will not work."
            )
            app.state.redis = None

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

    # Gracefully close redis client created at startup
    logger.info("Shutting down application, closing Redis client if it exists...")
    try:
        client = getattr(app.state, "redis", None)
        if client is not None:
            await client.aclose()
            await client.wait_closed()
            logger.info("Successfully closed Redis client at shutdown.")
    except Exception:
        logger.warning("Warning: Failed to close Redis client at shutdown.")
        pass


app = FastAPI(title="Deployment Control Plane", version="0.1.0", lifespan=lifespan)
app.add_middleware(LoggingMiddleware)  # log method, path, status, latency
app.add_middleware(SpanAttributesMiddleware)  # enrich tracing spans with request_id

# ── Monitoring routes ─────────────────────────────────────────────────────────

# include_monitoring_routes(app)  # GET /metrics  (Prometheus scrape)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(v1_router)
