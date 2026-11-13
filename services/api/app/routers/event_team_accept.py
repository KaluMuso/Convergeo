"""Accept an organiser door/manager invite by one-time token."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.teams import digest_invite_token
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/account/event-team", tags=["event-team"])


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class AcceptInviteRequest(StrictModel):
    token: str


class AcceptInviteResponse(StrictModel):
    event_id: str
    role: str
    status: str


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


@router.post("/accept", response_model=AcceptInviteResponse)
def accept_event_team_invite(
    body: AcceptInviteRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> AcceptInviteResponse:
    token = body.token.strip()
    if not token:
        raise AppError(code="invalid_token", message="Invite token is required", http_status=422)
    digest = digest_invite_token(token)
    invite = _single_row(
        service_client.client.table("event_team_invites")
        .select("id, event_id, role, invitee_phone, status, expires_at")
        .eq("token_digest", digest)
        .eq("status", "pending")
        .maybe_single()
        .execute()
    )
    if invite is None:
        raise AppError(code="invite_not_found", message="Invite is invalid", http_status=404)
    expires_raw = str(invite.get("expires_at") or "")
    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
    except ValueError as exc:
        raise AppError(
            code="invite_expired",
            message="Invite has expired",
            http_status=410,
        ) from exc
    if expires <= datetime.now(UTC):
        raise AppError(code="invite_expired", message="Invite has expired", http_status=410)
    profile = _single_row(
        service_client.client.table("profiles")
        .select("id, phone")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    phone = str(profile.get("phone") or "") if profile else ""
    if not phone or phone != str(invite["invitee_phone"]):
        raise AppError(
            code="invite_phone_mismatch",
            message="Sign in with the phone number this invite was sent to",
            http_status=403,
        )
    now = datetime.now(UTC).isoformat()
    member_payload = {
        "event_id": str(invite["event_id"]),
        "user_id": current_user.id,
        "role": invite["role"],
        "accepted_at": now,
    }
    member = _single_row(
        service_client.client.table("event_team_members")
        .upsert(member_payload, on_conflict="event_id,user_id")
        .execute()
    )
    if member is None:
        raise AppError(code="internal_error", message="Could not accept invite", http_status=500)
    service_client.client.table("event_team_invites").update(
        {
            "status": "accepted",
            "accepted_by": current_user.id,
            "accepted_at": now,
        }
    ).eq("id", str(invite["id"])).eq("status", "pending").execute()
    return AcceptInviteResponse(
        event_id=str(invite["event_id"]),
        role=str(invite["role"]),
        status="accepted",
    )
