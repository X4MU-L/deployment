import logging
import time
import uuid
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings
from app.core.context import get_request_id, get_trace_id, set_request_id

settings = get_settings()


class RequestContextFilter(logging.Filter):
    """Automatically inject request_id and trace_id into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.trace_id = get_trace_id() or "-"
        return True


def setup_logging(level: str = "INFO", name: str = settings.logger_name) -> None:
    """Configure structured logging with automatic request_id and trace_id injection."""
    # Create filter
    context_filter = RequestContextFilter()

    # Configure root logger with enhanced format
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s [%(levelname)s] %(name)s "
            "[request_id=%(request_id)s trace_id=%(trace_id)s] "
            "%(message)s"
        ),
    )

    # Apply filter to ALL existing handlers (added by basicConfig)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(context_filter)

    # Also add filter to the root logger itself
    root_logger.addFilter(context_filter)

    # Configure app logger
    app_logger = logging.getLogger(name)
    app_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    app_logger.addFilter(context_filter)


# Keep backward-compat alias used by old main.py
configure_logging = setup_logging


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log every request + response with latency, request_id, and trace_id."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Set request_id in context for this request
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        set_request_id(request_id)

        # Get logger after setup_logging() has configured filters
        logger = logging.getLogger(f"{settings.logger_name.lower()}.access")

        start = time.perf_counter()
        logger.info(
            "→ %s %s",
            request.method,
            request.url.path,
        )

        response: Response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "← %s %s status=%d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
