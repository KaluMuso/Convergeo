"""Vendor push devices: register / revoke Expo push tokens for the vendor mobile app.

Tokens are written only here (service role). Owner-only read is enforced by RLS on
``device_tokens``; nothing in this router ever returns the token itself after
registration, so a leaked response cannot be replayed to send pushes.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit_policies import enforce_registered_policy
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.base import StrictModel
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator

router = APIRouter(
    prefix="/vendor/devices",
    tags=["vendor-devices"],
    dependencies=[Depends(enforce_registered_policy)],
)

#: Active devices kept per vendor. A reinstall mints a new token, so the oldest are
#: revoked rather than refused.
MAX_ACTIVE_DEVICES = 10
_EXPO_TOKEN = re.compile(r"^Expo(?:nent)?PushToken\[[A-Za-z0-9_-]{8,128}\]$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class RegisterDeviceRequest(StrictModel):
    token: str = Field(min_length=20, max_length=200)
    platform: Literal["android", "ios"]
    app_version: str | None = Field(default=None, max_length=32)

    @field_validator("token")
    @classmethod
    def expo_token_shape(cls, value: str) -> str:
        value = value.strip()
        if not _EXPO_TOKEN.match(value):
            raise ValueError("token must be an Expo push token")
        return value


class RegisterDeviceResponse(StrictModel):
    id: str
    platform: str


class RevokeDeviceResponse(StrictModel):
    id: str
    revoked: bool


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _revoke_overflow(service_client: _ServiceRoleClient, vendor_id: str, now: str) -> None:
    active = _rows(
        service_client.client.table("device_tokens")
        .select("id, last_seen_at")
        .eq("vendor_id", vendor_id)
        .is_("revoked_at", "null")
        .order("last_seen_at", desc=True)
        .execute()
    )
    for stale in active[MAX_ACTIVE_DEVICES:]:
        service_client.client.table("device_tokens").update({"revoked_at": now}).eq(
            "id", stale["id"]
        ).execute()


@router.post("", response_model=RegisterDeviceResponse)
def register_device(
    body: RegisterDeviceRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> RegisterDeviceResponse:
    """Idempotent: re-registering a token refreshes it, and moves it if the phone changed hands."""
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    now = datetime.now(UTC).isoformat()
    existing = _rows(
        service_client.client.table("device_tokens")
        .select("id, user_id, revoked_at")
        .eq("token", body.token)
        .execute()
    )
    if (
        existing
        and existing[0].get("revoked_at") is None
        and str(existing[0]["user_id"]) != str(current_user.id)
    ):
        # An active token belongs to whoever registered it. Taking it over would send
        # that person's order alerts to this account, so it must be revoked by its owner first.
        raise AppError(
            code="conflict",
            message="This device is registered to another account",
            http_status=409,
            details={"message_key": "vendor.devices.owned_by_other"},
        )
    rows = _rows(
        service_client.client.table("device_tokens")
        .upsert(
            {
                "user_id": current_user.id,
                "vendor_id": vendor_id,
                "token": body.token,
                "platform": body.platform,
                "app_version": body.app_version,
                "last_seen_at": now,
                "revoked_at": None,
            },
            on_conflict="token",
        )
        .execute()
    )
    if not rows:
        raise AppError(code="internal_error", message="Could not register device", http_status=500)
    _revoke_overflow(service_client, vendor_id, now)
    return RegisterDeviceResponse(id=str(rows[0]["id"]), platform=body.platform)


@router.delete("/{device_id}", response_model=RevokeDeviceResponse)
def revoke_device(
    device_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> RevokeDeviceResponse:
    """Sign-out: stop pushes to this device. Only the owning user can revoke; others get 404."""
    if not _UUID.match(device_id):
        raise AppError(code="not_found", message="Device not found", http_status=404)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    updated = _rows(
        service_client.client.table("device_tokens")
        .update({"revoked_at": datetime.now(UTC).isoformat()})
        .eq("id", device_id)
        .eq("user_id", current_user.id)
        .eq("vendor_id", str(vendor["id"]))
        .execute()
    )
    if not updated:
        raise AppError(code="not_found", message="Device not found", http_status=404)
    return RevokeDeviceResponse(id=device_id, revoked=True)
