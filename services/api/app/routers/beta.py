"""Beta invite tooling + flag-controlled gate + feedback intake (M16-P09).

Routes (auto-discovered via the module-level ``router``):

* ``POST /beta/invites`` — admin: mint an invite code (capacity + optional expiry).
* ``GET  /beta/invites`` — admin: list invite codes with usage.
* ``GET  /beta/gate``    — public: is the site invite-only or public?
* ``POST /beta/redeem``  — public (IP rate-limited): redeem a code, or a no-op
  when the ``public_launch`` flag is ON (the gate opens with a flag flip — no deploy).
* ``POST /beta/feedback``— authenticated (rate-limited): floating-widget feedback
  (optional screenshot) enqueued to the admin inbox via the notification outbox.

The gate is a feature flag, not code: when ``feature_flags.public_launch`` is ON,
``/beta/redeem`` and ``/beta/gate`` report the site as public and the gate is a
no-op. Slot consumption is atomic + capacity-safe: ``/beta/redeem`` calls the
``public.redeem_beta_invite`` SECURITY DEFINER function (the only client path that
can decrement capacity — see migration 0030).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role, verify_supabase_jwt
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.services.notifications.dedupe import enqueue_outbox_row
from app.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/beta", tags=["beta"])

PUBLIC_LAUNCH_FLAG = "public_launch"

# Distinct redemption outcomes surfaced by public.redeem_beta_invite. "public"
# is added by the API when the gate is flag-open (no code required).
RedeemOutcome = Literal["redeemed", "invalid", "inactive", "expired", "exhausted", "public"]

FEEDBACK_CATEGORIES = frozenset({"bug", "idea", "confusing", "praise", "other"})
# Cap the optional canvas screenshot (data URL) so an oversized paste cannot bloat
# the outbox row / email. ~1.5MB of base64 ≈ ~1.1MB image — plenty for a screenshot.
MAX_SCREENSHOT_CHARS = 1_500_000
_SCREENSHOT_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,[A-Za-z0-9+/=\s]+$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class BetaInviteCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64, pattern=r"^[-._A-Za-z0-9]+$")
    capacity: int = Field(ge=1, le=100_000)
    expires_at: datetime | None = None
    active: bool = True
    note: str | None = Field(default=None, max_length=280)


class BetaInviteOut(BaseModel):
    id: UUID
    code: str
    capacity: int
    used_count: int
    remaining: int
    expires_at: datetime | None
    active: bool
    note: str | None
    created_at: datetime


class GateStatus(BaseModel):
    public_launch: bool
    invite_required: bool


class RedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class RedeemResult(BaseModel):
    outcome: RedeemOutcome
    granted: bool
    remaining: int
    invite_required: bool


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    category: str | None = Field(default=None, max_length=40)
    path: str | None = Field(default=None, max_length=300)
    screenshot: str | None = Field(default=None, max_length=MAX_SCREENSHOT_CHARS)


class FeedbackResult(BaseModel):
    ok: bool
    id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _invite_out(row: dict[str, Any]) -> BetaInviteOut:
    capacity = int(row["capacity"])
    used = int(row.get("used_count", 0))
    return BetaInviteOut(
        id=UUID(str(row["id"])),
        code=str(row["code"]),
        capacity=capacity,
        used_count=used,
        remaining=max(capacity - used, 0),
        expires_at=_parse_timestamp(row.get("expires_at")),
        active=bool(row.get("active", True)),
        note=row.get("note"),
        created_at=_parse_timestamp(row.get("created_at")) or datetime.now(UTC),
    )


def is_public_launch(service_client: ServiceRoleClient) -> bool:
    """Return whether the ``public_launch`` flag is ON (gate is a no-op / public).

    Reads the flag freshly so an admin flag flip opens the gate with no deploy.
    Defaults to invite-only (``False``) if the flag row is missing or unreadable.
    """
    try:
        response = (
            service_client.client.table("feature_flags")
            .select("enabled")
            .eq("flag", PUBLIC_LAUNCH_FLAG)
            .maybe_single()
            .execute()
        )
    except Exception:
        return False
    rows = _rows(response)
    if not rows:
        return False
    return bool(rows[0].get("enabled", False))


def _sanitize_text(value: str | None) -> str | None:
    """Strip control chars (incl. CR/LF) so nothing can inject into the outbox email."""
    if value is None:
        return None
    cleaned = _CONTROL_RE.sub(" ", value).strip()
    return cleaned or None


def _sanitize_body(value: str) -> str:
    """Keep newlines in the feedback body, drop other control chars, collapse CR."""
    without_cr = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "".join(ch for ch in without_cr if ch == "\n" or not _CONTROL_RE.match(ch))
    return cleaned.strip()


def _optional_user_id(request: Request, settings: Settings) -> str | None:
    """Best-effort caller identity: attach a user_id if a valid Bearer token is
    present, else treat as anonymous. Feedback is intentionally open (the widget
    floats on pre-login pages too) but IP rate-limited, so a bad token never 401s."""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        claims = verify_supabase_jwt(token, settings)
    except Exception:
        return None
    subject = claims.get("sub")
    return subject.strip() if isinstance(subject, str) and subject.strip() else None


def _rate_limit_beta(
    request: Request,
    service_client: ServiceRoleClient,
    *,
    scope: str,
    key_suffix: str,
    limit: int,
) -> None:
    key = f"{get_client_ip(request)}:{key_suffix}"
    allowed, retry_after = bump_rate_counter(
        scope=scope,
        key=key,
        window=timedelta(minutes=1),
        limit=limit,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="marketing.beta.errors.rateLimited",
            message="Too many requests",
        )


# ---------------------------------------------------------------------------
# Admin: invite management (service_role writes; audited)
# ---------------------------------------------------------------------------
@router.post("/invites", response_model=BetaInviteOut, status_code=201)
async def create_invite(
    body: BetaInviteCreate,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> BetaInviteOut:
    insert_row: dict[str, Any] = {
        "code": body.code,
        "capacity": body.capacity,
        "active": body.active,
        "note": _sanitize_text(body.note),
        "expires_at": body.expires_at.isoformat() if body.expires_at else None,
    }
    try:
        response = service_client.client.table("beta_invites").insert(insert_row).execute()
    except Exception as exc:  # unique(code) violation surfaces here
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise AppError(
                code="beta_code_exists",
                message="An invite with this code already exists",
                http_status=409,
                details={"code": body.code},
            ) from exc
        raise
    rows = _rows(response)
    if not rows:
        raise AppError(
            code="internal_error",
            message="Failed to create invite",
            http_status=500,
        )
    out = _invite_out(rows[0])
    recorder.record(
        action="beta.invite.create",
        entity_type="beta_invite",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
    )
    return out


@router.get("/invites", response_model=list[BetaInviteOut])
async def list_invites(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[BetaInviteOut]:
    response = (
        service_client.client.table("beta_invites")
        .select("id, code, capacity, used_count, expires_at, active, note, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return [_invite_out(row) for row in _rows(response)]


# ---------------------------------------------------------------------------
# Public: gate status + redemption
# ---------------------------------------------------------------------------
@router.get("/gate", response_model=GateStatus)
async def gate_status(
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> GateStatus:
    public = is_public_launch(service_client)
    return GateStatus(public_launch=public, invite_required=not public)


@router.post("/redeem", response_model=RedeemResult)
async def redeem_invite(
    body: RedeemRequest,
    request: Request,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> RedeemResult:
    # Flag flip opens the gate with no deploy: when public_launch is ON the gate
    # is a no-op and no code is required.
    if is_public_launch(service_client):
        return RedeemResult(
            outcome="public", granted=True, remaining=0, invite_required=False
        )

    _rate_limit_beta(
        request,
        service_client,
        scope="beta_redeem_ip",
        key_suffix="redeem",
        limit=10,
    )

    response = service_client.client.rpc(
        "redeem_beta_invite", {"p_code": body.code.strip()}
    ).execute()
    rows = _rows(response)
    if not rows:
        raise AppError(
            code="internal_error",
            message="Redemption failed",
            http_status=500,
        )
    outcome = str(rows[0].get("outcome", "invalid"))
    remaining = int(rows[0].get("remaining", 0) or 0)
    return RedeemResult(
        outcome=outcome,  # type: ignore[arg-type]
        granted=outcome == "redeemed",
        remaining=remaining,
        invite_required=True,
    )


# ---------------------------------------------------------------------------
# Authenticated: feedback widget -> admin inbox via outbox
# ---------------------------------------------------------------------------
@router.post("/feedback", response_model=FeedbackResult, status_code=201)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FeedbackResult:
    user_id = _optional_user_id(request, settings)
    _rate_limit_beta(
        request,
        service_client,
        scope="beta_feedback_ip",
        key_suffix="feedback",
        limit=20,
    )

    message = _sanitize_body(body.message)
    if not message:
        raise AppError(
            code="validation_error",
            message="Feedback message is required",
            http_status=422,
            details={"message": "must not be empty"},
        )

    category = body.category if body.category in FEEDBACK_CATEGORIES else "other"

    screenshot: str | None = None
    if body.screenshot:
        candidate = body.screenshot.strip()
        if _SCREENSHOT_RE.match(candidate):
            screenshot = candidate
        else:
            raise AppError(
                code="validation_error",
                message="Screenshot must be a base64 image data URL",
                http_status=422,
                details={"screenshot": "expected data:image/(png|jpeg|webp);base64,..."},
            )

    feedback_id = str(uuid4())
    payload: dict[str, Any] = {
        "feedback_id": feedback_id,
        "user_id": user_id,
        "category": category,
        "message": message,
        "path": _sanitize_text(body.path),
        "has_screenshot": screenshot is not None,
    }
    if screenshot is not None:
        payload["screenshot"] = screenshot

    # Unique dedupe_key per submission (feedback is not deduplicated); email
    # channel routes to the admin support inbox via the existing outbox dispatcher.
    row = enqueue_outbox_row(
        service_client.client,
        event_type=f"beta_feedback:{feedback_id}",
        entity_id=feedback_id,
        channel="email",
        template="beta_feedback",
        payload=payload,
    )
    if row is None:
        raise AppError(
            code="internal_error",
            message="Failed to record feedback",
            http_status=500,
        )
    return FeedbackResult(ok=True, id=feedback_id)
