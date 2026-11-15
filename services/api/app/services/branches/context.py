"""Acting-branch request scope.

An owner with several branches (all sharing ``vendors.owner_user_id``) picks the
branch they are working on in the vendor app; the app sends it as the
``X-Vendor-Branch`` header. The middleware below parses it into a context
variable and :func:`scope_owner_vendor_query` narrows every "vendor owned by the
caller" lookup to that branch.

Security: the header only ever NARROWS a query that is already filtered by
``owner_user_id = caller`` — it can never reach another owner's storefront. A
malformed value is ignored (treated as absent). Without the header the lookup is
unchanged, so single-shop vendors (every vendor while ``multi_branch`` is off)
behave exactly as before.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Final
from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

BRANCH_HEADER: Final = "x-vendor-branch"

_acting_branch: ContextVar[str | None] = ContextVar("acting_branch_id", default=None)

def parse_branch_header(raw: str | None) -> str | None:
    """Return a canonical UUID string, or ``None`` for a missing/garbage value."""
    if not raw:
        return None
    try:
        return str(UUID(raw.strip()))
    except (ValueError, AttributeError):
        return None


def acting_branch_id() -> str | None:
    return _acting_branch.get()


def set_acting_branch_id(branch_id: str | None) -> Any:
    """Set the acting branch for the current context; returns a reset token."""
    return _acting_branch.set(parse_branch_header(branch_id))


def reset_acting_branch_id(token: Any) -> None:
    _acting_branch.reset(token)


def scope_owner_vendor_query[QueryT](query: QueryT) -> QueryT:
    """Narrow an owner-scoped ``vendors`` query to the acting branch, if any."""
    branch_id = acting_branch_id()
    if branch_id is None:
        return query
    narrowed: QueryT = query.eq("id", branch_id)  # type: ignore[attr-defined]
    return narrowed


class ActingBranchMiddleware:
    """Pure ASGI middleware so the context variable reaches the endpoint."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw: str | None = None
        for key, value in scope.get("headers") or []:
            if key.decode("latin-1").lower() == BRANCH_HEADER:
                raw = value.decode("latin-1")
                break
        token = _acting_branch.set(parse_branch_header(raw))
        try:
            await self.app(scope, receive, send)
        finally:
            _acting_branch.reset(token)
