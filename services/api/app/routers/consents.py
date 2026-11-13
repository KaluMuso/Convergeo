"""Customer consent to share delivery details with a third-party courier (Zambia DPA 2021).

The founder decided (2026-11-13) that customers give this consent in the app, from the
privacy settings page or the checkout notice. Each answer is a new row in
`public.privacy_consents` (append-only) carrying the notice version and a timestamp; the
latest row is the current answer. A withdrawal is simply a newer row with
`granted = false`.

Courier dispatch (`dispatch_requests`) refuses an order whose customer has not
currently consented — enforced by the API and again by a database trigger. Pickup orders
never reach a courier and need no consent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.errors import AppError
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/account", tags=["privacy-consents"])

DELIVERY_PARTNER_PURPOSE: Literal["delivery_partner_share"] = "delivery_partner_share"
# Bump when the wording of `account.privacy.deliveryConsent.*` / the checkout notice
# changes materially; older consents then read as "not given for this version".
DELIVERY_PARTNER_NOTICE_VERSION = "2026-11-13"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class ConsentOut(BaseModel):
    purpose: Literal["delivery_partner_share"]
    granted: bool
    version: str
    current_version: str
    recorded_at: datetime | None


class ConsentIn(BaseModel):
    granted: bool
    source: Literal["settings", "checkout"]
    version: Literal["2026-11-13"]


def latest_delivery_consent(service: ServiceRoleClient, user_id: str) -> dict[str, Any] | None:
    data = getattr(
        service.client.table("privacy_consents")
        .select("granted,version,recorded_at")
        .eq("user_id", user_id)
        .eq("purpose", DELIVERY_PARTNER_PURPOSE)
        .order("recorded_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute(),
        "data",
        None,
    )
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def has_current_delivery_consent(service: ServiceRoleClient, user_id: str) -> bool:
    row = latest_delivery_consent(service, user_id)
    return bool(row and row.get("granted") is True)


def _out(row: dict[str, Any] | None) -> ConsentOut:
    return ConsentOut(
        purpose=DELIVERY_PARTNER_PURPOSE,
        granted=bool(row and row.get("granted") is True),
        version=str(row.get("version")) if row else DELIVERY_PARTNER_NOTICE_VERSION,
        current_version=DELIVERY_PARTNER_NOTICE_VERSION,
        recorded_at=row.get("recorded_at") if row else None,
    )


@router.get("/consents/delivery-partner", response_model=ConsentOut)
def get_delivery_partner_consent(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ConsentOut:
    return _out(latest_delivery_consent(service, user.id))


@router.put("/consents/delivery-partner", response_model=ConsentOut)
def set_delivery_partner_consent(
    body: ConsentIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ConsentOut:
    data = getattr(
        service.client.table("privacy_consents")
        .insert(
            {
                "user_id": user.id,
                "purpose": DELIVERY_PARTNER_PURPOSE,
                "version": body.version,
                "granted": body.granted,
                "source": body.source,
            }
        )
        .execute(),
        "data",
        None,
    )
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise AppError(
            code="consent_write_failed", message="Consent was not recorded", http_status=500
        )
    return _out(data[0])
