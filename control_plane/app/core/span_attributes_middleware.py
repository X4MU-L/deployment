"""
Middleware to enrich OpenTelemetry spans with custom attributes.

This must run AFTER RequestIdMiddleware so the request_id is available,
and it runs within the FastAPI instrumentation span.
"""

from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.context import get_request_id

try:
    from opentelemetry import trace

    OTEL_AVAILABLE = True
except ImportError:
    trace = None  # type: ignore[assignment]
    OTEL_AVAILABLE = False


class SpanAttributesMiddleware(BaseHTTPMiddleware):
    """Enrich the current OpenTelemetry span with request-scoped attributes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Add custom attributes to the span created by FastAPI instrumentation
        if OTEL_AVAILABLE and trace is not None:
            span = trace.get_current_span()
            if span.is_recording():
                # Add request_id for log correlation
                request_id = get_request_id()
                if request_id:
                    span.set_attribute("request.id", request_id)

                # Add other useful attributes
                span.set_attribute(
                    "http.client_ip", request.client.host if request.client else "unknown"
                )

        return await call_next(request)
