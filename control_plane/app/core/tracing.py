"""OpenTelemetry tracing setup and helpers.

Design choices:
- Fully optional: if opentelemetry packages are not installed the module
  degrades to no-ops so the rest of the codebase never needs try/except guards.
- `@trace_span()` works on both sync and async functions.
- `get_tracer()` can be injected into services and repos for fine-grained spans.
- For tests: `create_test_tracer_provider()` installs an in-memory provider.
"""

from __future__ import annotations

import contextlib
from asyncio import iscoroutinefunction
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from app.core.config import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

import logging

settings = get_settings()

logger = logging.getLogger(f"{settings.logger_name.lower()}.tracing")

# ── Optional OTLP exporter ────────────────────────────────────────────────────
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except Exception:
    OTLPSpanExporter = None  # type: ignore[assignment,misc]

# ── Optional SQLAlchemy instrumentation ───────────────────────────────────────
try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLALCHEMY_INSTRUMENTOR_AVAILABLE = True
except Exception:
    SQLAlchemyInstrumentor = None  # type: ignore[assignment,misc]
    SQLALCHEMY_INSTRUMENTOR_AVAILABLE = False

# ── Optional OpenTelemetry core ───────────────────────────────────────────────
try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    OTEL_AVAILABLE = True
except Exception:
    trace = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment,misc]
    BatchSpanProcessor = None  # type: ignore[assignment,misc]
    ConsoleSpanExporter = None  # type: ignore[assignment,misc]
    InMemorySpanExporter = None  # type: ignore[assignment,misc]
    SimpleSpanProcessor = None  # type: ignore[assignment,misc]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    LoggingInstrumentor = None  # type: ignore[assignment]
    OTEL_AVAILABLE = False


# ── Public API ────────────────────────────────────────────────────────────────


def setup_tracing(
    *,
    service_name: str | None = None,
    exporter: Literal["console", "inmemory", "otlp"] = "console",
    otlp_endpoint: str | None = None,
    otlp_insecure: bool = True,
) -> None:
    """Configure OpenTelemetry tracing provider (no-op when packages are not installed).

    Note: This sets up the tracer provider. Call instrument_fastapi_app() separately
    to instrument a FastAPI application.

    Args:
        service_name: Resource attribute ``service.name``.
        exporter: ``"console"`` | ``"inmemory"`` (useful for tests) | ``"otlp"``.
        otlp_endpoint: gRPC endpoint for the OTLP exporter.
        otlp_insecure: Disable TLS on the OTLP connection (local collector).
    """
    if not OTEL_AVAILABLE:
        logger.debug("OpenTelemetry packages not available; tracing disabled")
        return

    if exporter == "otlp" and OTLPSpanExporter is None:
        logger.warning("OTLP exporter requested but package not installed; falling back to console")
        exporter = "console"

    try:
        if TracerProvider is None:
            return

        resource = Resource.create({"service.name": service_name or "booking-app"})
        provider = TracerProvider(resource=resource)

        if exporter == "otlp" and OTLPSpanExporter is not None and BatchSpanProcessor is not None:
            kwargs: dict = {}
            if otlp_endpoint:
                kwargs["endpoint"] = otlp_endpoint
            if otlp_insecure:
                kwargs["insecure"] = True
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**kwargs)))
            logger.info("Tracing: OTLPSpanExporter (endpoint=%s)", otlp_endpoint)

        elif (
            exporter == "inmemory"
            and InMemorySpanExporter is not None
            and SimpleSpanProcessor is not None
        ):
            mem = InMemorySpanExporter()
            provider.add_span_processor(SimpleSpanProcessor(mem))
            logger.info("Tracing: InMemorySpanExporter (test mode)")

        else:  # console (default)
            if BatchSpanProcessor is not None and ConsoleSpanExporter is not None:
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                logger.info("Tracing: ConsoleSpanExporter")

        if trace is not None:
            trace.set_tracer_provider(provider)

        # Inject trace_id / span_id into log records
        try:
            if LoggingInstrumentor is not None:
                LoggingInstrumentor().instrument(set_logging_format=True)
        except Exception:
            logger.debug("LoggingInstrumentor failed; continuing")

    except Exception as exc:
        logger.warning("OpenTelemetry setup failed: %s", exc)


def instrument_fastapi_app(app: FastAPI) -> None:
    """Instrument a FastAPI application for OpenTelemetry tracing.

    This should be called immediately after creating the FastAPI app instance,
    before adding middleware or routes.

    Args:
        app: The FastAPI application instance to instrument.
    """
    if not OTEL_AVAILABLE:
        logger.debug("OpenTelemetry not available; skipping FastAPI instrumentation")
        return

    if FastAPIInstrumentor is None:
        logger.debug("FastAPIInstrumentor not available; skipping")
        return

    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("✅ FastAPI auto-instrumentation enabled - HTTP spans will trace all requests")
    except Exception as exc:
        logger.warning("FastAPIInstrumentor failed: %s; continuing", exc)


def get_tracer(name: str = "app"):
    """Return an OpenTelemetry tracer (or a no-op when OTEL is unavailable)."""
    if not OTEL_AVAILABLE or trace is None:

        class _Noop:
            def start_as_current_span(self, *_a, **_kw):
                return contextlib.nullcontext()

            def start_span(self, *_a, **_kw):
                return None

        return _Noop()

    return trace.get_tracer(name)


def get_trace_id() -> str:
    """Return the current OpenTelemetry trace ID as a hex string, or ``"0"`` when unavailable."""
    if not OTEL_AVAILABLE or trace is None:
        return "0"
    try:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception as exc:
        logger.debug("Failed to get trace ID from OpenTelemetry context; returning '0': %s", exc)
        pass
    return "0"


def get_traceparent() -> str | None:
    """Serialize the current span context as a W3C ``traceparent`` string.

    Returns a string like::

        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
         ^^ ^^^^^^^^^^^^^^^^trace_id^^^^^^^^ ^^^parent_span^^ ^^

    or ``None`` when there is no active span (tracing not configured).

    Store this string in the database next to the entity being traced
    (e.g. ``payments.origin_traceparent``).  Pass it later to
    ``extract_context()`` — even across process / time boundaries — to
    attach a new span to the same trace.
    """
    if not OTEL_AVAILABLE or trace is None:
        return None
    try:
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)  # type: ignore[name-defined]
        return carrier.get("traceparent")  # None when no active span
    except Exception as exc:
        logger.debug("Failed to inject traceparent: %s", exc)
        return None


def extract_context(traceparent: str | None):
    """Restore an OTel context from a stored W3C ``traceparent`` string.

    Typical usage inside a Celery task::

        ctx = extract_context(payment.origin_traceparent)
        with get_tracer(__name__).start_as_current_span("expire_booking", context=ctx):
            ...  # this span appears as a child of the original HTTP request

    How this works
    --------------
    A span ending does **not** invalidate the trace.  A ``traceparent`` is just
    a tiny string containing the ``trace_id`` and ``parent_span_id``.  Passing
    it to this function recreates the OTel ``Context`` object that OTel needs
    to attach new child spans to the same trace — even minutes later, in a
    completely different process.

    If *traceparent* is ``None`` the returned context is the current context,
    so the caller's span simply has no remote parent.
    """
    if not OTEL_AVAILABLE or not traceparent:
        try:
            from opentelemetry import context as _ctx

            return _ctx.get_current()
        except Exception:
            return None
    try:
        carrier = {"traceparent": traceparent}
        return TraceContextTextMapPropagator().extract(carrier)  # type: ignore[name-defined]
    except Exception as exc:
        logger.debug("Failed to extract traceparent context: %s", exc)
        return None


def trace_span(name: str | None = None):
    """Decorator that wraps sync/async functions in an OpenTelemetry span.

    Usage::

        @trace_span()
        def my_repo_method(self, ...): ...

        @trace_span("db.query.bookings")
        async def list_bookings(self, ...): ...

    Safe to use everywhere — degrades to a transparent wrapper when OTEL is
    not installed.
    """

    def _decorator(func: Callable):
        import functools
        from typing import Any, cast

        @functools.wraps(func)
        def _sync_wrapper(*args, **kwargs):
            tracer = get_tracer(func.__module__)
            span_name = name or f"{func.__module__}.{func.__name__}"
            with cast(Any, tracer.start_as_current_span(span_name)):
                return func(*args, **kwargs)

        @functools.wraps(func)
        async def _async_wrapper(*args, **kwargs):
            tracer = get_tracer(func.__module__)
            span_name = name or f"{func.__module__}.{func.__name__}"
            span_cm = tracer.start_as_current_span(span_name)
            try:
                if hasattr(span_cm, "__aenter__"):
                    async with cast(Any, span_cm):
                        return await func(*args, **kwargs)
                else:
                    with cast(Any, span_cm):
                        return await func(*args, **kwargs)
            except Exception:
                # Fallback: if tracer context manager fails, run function directly
                return await func(*args, **kwargs)

        return _async_wrapper if iscoroutinefunction(func) else _sync_wrapper

    return _decorator


# ── Test helpers ──────────────────────────────────────────────────────────────


def create_test_tracer_provider():
    """Install an InMemorySpanExporter and return ``(provider, exporter)``.

    Example::

        provider, exporter = create_test_tracer_provider()
        # ... call code that emits spans ...
        spans = exporter.get_finished_spans()
    """
    if (
        not OTEL_AVAILABLE
        or TracerProvider is None
        or InMemorySpanExporter is None
        or SimpleSpanProcessor is None
        or trace is None
    ):
        raise RuntimeError("OpenTelemetry packages are not available for test tracer")

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider, exporter


def reset_tracing_provider() -> None:
    """Reset tracer provider to no-op (test teardown helper)."""
    if OTEL_AVAILABLE and trace is not None and TracerProvider is not None:
        with contextlib.suppress(Exception):
            trace.set_tracer_provider(TracerProvider())


def instrument_sqlalchemy(engine) -> None:
    """Auto-instrument SQLAlchemy engine to trace all database queries.

    This adds automatic spans for every SQL query executed through the engine:
    - SELECT queries
    - INSERT/UPDATE/DELETE queries
    - Transaction commits/rollbacks
    - Connection pool operations

    Each span includes:
    - Query duration
    - SQL statement (sanitized, no sensitive data)
    - Database name
    - Table names

    Args:
        engine: SQLAlchemy engine (async or sync)

    Example:
        >>> from sqlalchemy.ext.asyncio import create_async_engine
        >>> engine = create_async_engine("postgresql+asyncpg://...")
        >>> instrument_sqlalchemy(engine)  # Auto-traces all queries

    Note:
        - For async engines, pass engine.sync_engine
        - Safe to call multiple times (no-op if already instrumented)
        - No-op if opentelemetry-instrumentation-sqlalchemy not installed
    """
    if not SQLALCHEMY_INSTRUMENTOR_AVAILABLE or SQLAlchemyInstrumentor is None:
        logger.debug("SQLAlchemy instrumentation not available (package not installed)")
        return

    if not OTEL_AVAILABLE:
        logger.debug("OpenTelemetry not configured, skipping SQLAlchemy instrumentation")
        return

    try:
        # For async engines, instrument the sync_engine
        actual_engine = getattr(engine, "sync_engine", engine)

        SQLAlchemyInstrumentor().instrument(
            engine=actual_engine,
            enable_commenter=True,  # Add trace context to SQL comments (/* traceparent=... */)
            skip_dep_check=True,  # Skip dependency version checks
        )
        logger.info("✅ SQLAlchemy auto-instrumentation enabled - all queries will be traced")
    except Exception as exc:
        logger.warning("Failed to instrument SQLAlchemy engine: %s", exc)
