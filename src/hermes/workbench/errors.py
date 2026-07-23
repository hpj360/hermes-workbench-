"""Error hierarchy for the Workbench layer.

Each error maps to an HTTP status code via status_code_for(), used by both
the CLI (exit codes) and the dashboard API (HTTP responses).
"""

from __future__ import annotations


class WorkbenchError(Exception):
    """Base class for all Workbench errors."""


class AuthError(WorkbenchError):
    """Authentication failed (401)."""


class ValidationError(WorkbenchError):
    """Input validation failed (400)."""


class NotFoundError(WorkbenchError):
    """Requested resource not found (404)."""


class StateError(WorkbenchError):
    """Illegal state transition or conflict (409)."""


class UpstreamError(WorkbenchError):
    """Upstream service error (502)."""


_STATUS_CODES: dict[type[Exception], int] = {
    ValidationError: 400,
    AuthError: 401,
    NotFoundError: 404,
    StateError: 409,
    UpstreamError: 502,
}


def status_code_for(exc: Exception) -> int:
    """Return the HTTP status code for *exc*, defaulting to 500."""
    for exc_type, code in _STATUS_CODES.items():
        if isinstance(exc, exc_type):
            return code
    return 500
