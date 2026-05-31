"""
Request-scoped context storage using Python contextvars.
Allows request_id and trace_id to be accessed anywhere without threading issues.
"""

from contextvars import ContextVar

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


def get_trace_id() -> str:
    """Return the current OpenTelemetry trace ID, or ``"0"`` when unavailable.

    Reads from the active span context so it always reflects the *current*
    request — no manual propagation needed.
    """
    from app.core.tracing import get_trace_id as _otel_trace_id  # local import avoids circular

    return _otel_trace_id()
