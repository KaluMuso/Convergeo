"""Safe, low-cardinality observability for outbound dependency failures.

The API must distinguish a timeout from a reset or an unavailable dependency so
operators can diagnose a customer-facing fetch failure without putting request
URLs, credentials, response bodies, or exception text into structured logs.
"""

from __future__ import annotations

import errno
import logging
from enum import StrEnum
from typing import Final

import httpx

logger = logging.getLogger(__name__)


class UpstreamFailureKind(StrEnum):
    """Stable, non-sensitive labels for dependency and network failures."""

    TIMEOUT = "timeout"
    CONNECTION_RESET = "connection_reset"
    CONNECTION_REFUSED = "connection_refused"
    NETWORK_UNREACHABLE = "network_unreachable"
    NETWORK_ERROR = "network_error"
    UNEXPECTED_STATUS = "unexpected_status"
    UNKNOWN = "unknown"


_NETWORK_UNREACHABLE_ERRNOS: Final = frozenset({errno.ENETUNREACH, errno.EHOSTUNREACH})


def _os_error_from_chain(exc: BaseException) -> OSError | None:
    """Find an ``OSError`` cause without rendering its potentially sensitive text."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError):
            return current
        current = current.__cause__ or current.__context__
    return None


def classify_httpx_error(exc: httpx.HTTPError) -> UpstreamFailureKind:
    """Map HTTPX transport errors to a bounded operator-facing vocabulary."""

    if isinstance(exc, httpx.TimeoutException):
        return UpstreamFailureKind.TIMEOUT

    os_error = _os_error_from_chain(exc)
    if os_error is not None:
        if os_error.errno == errno.ECONNRESET:
            return UpstreamFailureKind.CONNECTION_RESET
        if os_error.errno == errno.ECONNREFUSED:
            return UpstreamFailureKind.CONNECTION_REFUSED
        if os_error.errno in _NETWORK_UNREACHABLE_ERRNOS:
            return UpstreamFailureKind.NETWORK_UNREACHABLE

    if isinstance(exc, httpx.NetworkError):
        return UpstreamFailureKind.NETWORK_ERROR
    return UpstreamFailureKind.UNKNOWN


def log_upstream_failure(
    *,
    dependency: str,
    failure_kind: UpstreamFailureKind,
    status_code: int | None = None,
) -> None:
    """Emit structured, low-cardinality data with no URL or exception payload."""

    extra: dict[str, str | int] = {
        "dependency": dependency,
        "failure_kind": failure_kind.value,
    }
    if status_code is not None:
        extra["status_code"] = status_code
    logger.warning("upstream_dependency_failed", extra=extra)
