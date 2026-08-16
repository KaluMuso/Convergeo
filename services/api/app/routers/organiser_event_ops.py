"""Event-scoped team members and promo codes (organiser)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.events.teams import (
    EDIT_ROLES,
    FINANCE_ROLES,
    digest_invite_token,
    list_team_members,
    mint_invite_token,
    normalize_invite_phone,
    require_event_role,
)
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

router = APIRouter(prefix="/organiser/events", tags=["organiser-event-ops"])

TeamRole = Literal["owner", "manager", "door"]
DiscountKind = Literal["percent", "fixed"]


class TeamMemberOut(StrictModel):
    id: str
    user_id: str
    role: TeamRole
    accepted_at: str | None = None


class TeamInviteOut(StrictModel):
    id: str
    role: Literal["manager", "door"]
    invitee_phone: str
    status: str
    expires_at: str


class TeamListResponse(StrictModel):
    members: list[TeamMemberOut]
    invites: list[TeamInviteOut] = Field(default_factory=list)


class TeamAddRequest(StrictModel):
    role: Literal["manager", "door"]
    user_id: str | None = None
    phone: str | None = None

    @model_validator(mode="after")
    def require_user_or_phone(self) -> TeamAddRequest:
        if not (self.user_id and self.user_id.strip()) and not (self.phone and self.phone.strip()):
            raise ValueError("phone or user_id is required")
        return self


class TeamAddResponse(StrictModel):
    member: TeamMemberOut | None = None
    invite: TeamInviteOut | None = None
    invite_token: str | None = None


class PromoOut(StrictModel):
    id: str
    code: str
    discount_kind: DiscountKind
    discount_value: int
    max_redemptions: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    active: bool = True


class PromoListResponse(StrictModel):
    items: list[PromoOut]


class PromoCreateRequest(StrictModel):
    code: str = Field(min_length=3, max_length=32)
    discount_kind: DiscountKind
    discount_value: int = Field(gt=0)
    max_redemptions: int | None = Field(default=None, gt=0)
    starts_at: str | None = None
    ends_at: str | None = None


class AffiliateOut(StrictModel):
    id: str
    code: str
    commission_bps: int
    active: bool = True


class AffiliateListResponse(StrictModel):
    items: list[AffiliateOut]


class AffiliateCreateRequest(StrictModel):
    code: str = Field(min_length=3, max_length=32)


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _load_vendor_for_owner(service_client: ServiceRoleClient, owner_user_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id")
        .eq("owner_user_id", owner_user_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return row


def _load_owned_event(
    service_client: ServiceRoleClient, *, event_id: str, vendor_id: str
) -> dict[str, Any]:
    response = (
        service_client.client.table("events")
        .select("id, organiser_vendor_id")
        .eq("id", event_id)
        .eq("organiser_vendor_id", vendor_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Event not found", http_status=404)
    return row


def _require_owner(
    service_client: ServiceRoleClient, *, event_id: str, user_id: str, vendor_id: str
) -> None:
    event = _load_owned_event(service_client, event_id=event_id, vendor_id=vendor_id)
    del event
    require_event_role(
        service_client.client,
        event_id=event_id,
        user_id=user_id,
        organiser_owner_user_id=user_id,
        allowed=FINANCE_ROLES,
    )


@router.get("/{event_id}/team", response_model=TeamListResponse)
def get_event_team(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> TeamListResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _load_owned_event(service_client, event_id=event_id, vendor_id=str(vendor["id"]))
    require_event_role(
        service_client.client,
        event_id=event_id,
        user_id=current_user.id,
        organiser_owner_user_id=current_user.id,
        allowed=EDIT_ROLES,
    )
    members = list_team_members(service_client.client, event_id=event_id)
    invite_rows = _rows(
        service_client.client.table("event_team_invites")
        .select("id, role, invitee_phone, status, expires_at")
        .eq("event_id", event_id)
        .eq("status", "pending")
        .execute()
    )
    return TeamListResponse(
        members=[
            TeamMemberOut(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                role=cast(TeamRole, row["role"]),
                accepted_at=str(row["accepted_at"]) if row.get("accepted_at") else None,
            )
            for row in members
            if row.get("role") in {"owner", "manager", "door"}
        ],
        invites=[
            TeamInviteOut(
                id=str(row["id"]),
                role=cast(Literal["manager", "door"], row["role"]),
                invitee_phone=str(row["invitee_phone"]),
                status=str(row["status"]),
                expires_at=str(row["expires_at"]),
            )
            for row in invite_rows
            if row.get("role") in {"manager", "door"}
        ],
    )


@router.post("/{event_id}/team", response_model=TeamAddResponse)
def add_event_team_member(
    event_id: str,
    body: TeamAddRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> TeamAddResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_owner(
        service_client, event_id=event_id, user_id=current_user.id, vendor_id=str(vendor["id"])
    )
    user_id = body.user_id.strip() if body.user_id else None
    phone = normalize_invite_phone(body.phone) if body.phone else None
    if phone and not user_id:
        profile = _single_row(
            service_client.client.table("profiles")
            .select("id, phone")
            .eq("phone", phone)
            .maybe_single()
            .execute()
        )
        if profile and profile.get("id"):
            user_id = str(profile["id"])
    if user_id:
        payload = {
            "event_id": event_id,
            "user_id": user_id,
            "role": body.role,
            "invited_by": current_user.id,
            "accepted_at": datetime.now(UTC).isoformat(),
        }
        response = (
            service_client.client.table("event_team_members")
            .upsert(payload, on_conflict="event_id,user_id")
            .execute()
        )
        row = _single_row(response)
        if row is None:
            raise AppError(
                code="internal_error", message="Could not add team member", http_status=500
            )
        return TeamAddResponse(
            member=TeamMemberOut(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                role=cast(TeamRole, row["role"]),
                accepted_at=str(row["accepted_at"]) if row.get("accepted_at") else None,
            )
        )
    assert phone is not None
    token = mint_invite_token()
    expires_at = (datetime.now(UTC) + timedelta(days=14)).isoformat()
    invite_payload = {
        "id": str(uuid4()),
        "event_id": event_id,
        "role": body.role,
        "invitee_phone": phone,
        "token_digest": digest_invite_token(token),
        "invited_by": current_user.id,
        "status": "pending",
        "expires_at": expires_at,
    }
    invite_response = (
        service_client.client.table("event_team_invites").insert(invite_payload).execute()
    )
    invite_row = _single_row(invite_response)
    if invite_row is None:
        raise AppError(code="internal_error", message="Could not create invite", http_status=500)
    return TeamAddResponse(
        invite=TeamInviteOut(
            id=str(invite_row["id"]),
            role=cast(Literal["manager", "door"], invite_row["role"]),
            invitee_phone=str(invite_row["invitee_phone"]),
            status=str(invite_row["status"]),
            expires_at=str(invite_row["expires_at"]),
        ),
        invite_token=token,
    )


@router.delete("/{event_id}/team/{member_id}")
def revoke_event_team_member(
    event_id: str,
    member_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> dict[str, str]:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_owner(
        service_client, event_id=event_id, user_id=current_user.id, vendor_id=str(vendor["id"])
    )
    service_client.client.table("event_team_members").update(
        {"revoked_at": datetime.now(UTC).isoformat()}
    ).eq("id", member_id).eq("event_id", event_id).neq("role", "owner").execute()
    return {"status": "revoked"}


def _promo_out(row: dict[str, Any]) -> PromoOut:
    starts = row.get("starts_at")
    ends = row.get("ends_at")
    return PromoOut(
        id=str(row["id"]),
        code=str(row["code"]),
        discount_kind=cast(DiscountKind, row["discount_kind"]),
        discount_value=int(row["discount_value"]),
        max_redemptions=(
            int(row["max_redemptions"]) if row.get("max_redemptions") is not None else None
        ),
        starts_at=datetime.fromisoformat(str(starts).replace("Z", "+00:00")) if starts else None,
        ends_at=datetime.fromisoformat(str(ends).replace("Z", "+00:00")) if ends else None,
        active=bool(row.get("active", True)),
    )


@router.get("/{event_id}/promos", response_model=PromoListResponse)
def list_event_promos(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PromoListResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _load_owned_event(service_client, event_id=event_id, vendor_id=str(vendor["id"]))
    rows = _rows(
        service_client.client.table("event_promo_codes")
        .select(
            "id, code, discount_kind, discount_value, max_redemptions, starts_at, ends_at, active"
        )
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .execute()
    )
    return PromoListResponse(items=[_promo_out(row) for row in rows])


@router.post("/{event_id}/promos", response_model=PromoOut)
def create_event_promo(
    event_id: str,
    body: PromoCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> PromoOut:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_owner(
        service_client, event_id=event_id, user_id=current_user.id, vendor_id=str(vendor["id"])
    )
    if body.discount_kind == "percent" and body.discount_value > 100:
        raise AppError(
            code="promo_percent_invalid",
            message="Percent discounts cannot exceed 100",
            http_status=422,
        )
    payload: dict[str, Any] = {
        "event_id": event_id,
        "code": body.code.strip().upper(),
        "discount_kind": body.discount_kind,
        "discount_value": body.discount_value,
        "max_redemptions": body.max_redemptions,
        "starts_at": body.starts_at,
        "ends_at": body.ends_at,
        "active": True,
    }
    response = service_client.client.table("event_promo_codes").insert(payload).execute()
    row = _single_row(response)
    if row is None:
        raise AppError(code="internal_error", message="Could not create promo", http_status=500)
    return _promo_out(row)


def _affiliate_out(row: dict[str, Any]) -> AffiliateOut:
    return AffiliateOut(
        id=str(row["id"]),
        code=str(row["code"]),
        commission_bps=int(row.get("commission_bps") or 0),
        active=bool(row.get("active", True)),
    )


@router.get("/{event_id}/affiliates", response_model=AffiliateListResponse)
def list_event_affiliates(
    event_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> AffiliateListResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _load_owned_event(service_client, event_id=event_id, vendor_id=str(vendor["id"]))
    rows = _rows(
        service_client.client.table("event_affiliates")
        .select("id, code, commission_bps, active")
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .execute()
    )
    return AffiliateListResponse(items=[_affiliate_out(row) for row in rows])


@router.post("/{event_id}/affiliates", response_model=AffiliateOut)
def create_event_affiliate(
    event_id: str,
    body: AffiliateCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> AffiliateOut:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    _require_owner(
        service_client, event_id=event_id, user_id=current_user.id, vendor_id=str(vendor["id"])
    )
    payload = {
        "event_id": event_id,
        "code": body.code.strip().upper(),
        "commission_bps": 0,
        "active": True,
    }
    response = service_client.client.table("event_affiliates").insert(payload).execute()
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="internal_error", message="Could not create affiliate code", http_status=500
        )
    return _affiliate_out(row)
