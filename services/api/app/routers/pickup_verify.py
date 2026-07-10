from __future__ import annotations

from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.pickup.verify import PickupVerifyResult, verify_pickup_by_pin, verify_pickup_by_qr
from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

router = APIRouter(prefix="/vendor/pickup", tags=["pickup"])


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class VerifyPickupRequest(StrictModel):
    qr_token: str | None = Field(default=None, min_length=1)
    order_id: str | None = None
    pin: str | None = Field(default=None, min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_method(self) -> VerifyPickupRequest:
        has_qr = bool(self.qr_token and self.qr_token.strip())
        has_pin = bool(self.order_id and self.pin and self.pin.strip())
        if has_qr == has_pin:
            raise ValueError("Provide exactly one of qr_token or (order_id + pin)")
        return self


class VerifyPickupResponse(StrictModel):
    order_id: str
    from_status: str
    to_status: str
    event: str
    token_version: int


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _load_vendor_for_owner(
    service_client: _ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
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


def _to_response(result: PickupVerifyResult) -> VerifyPickupResponse:
    return VerifyPickupResponse(
        order_id=result.order_id,
        from_status=result.transition.from_status.value,
        to_status=result.transition.to_status.value,
        event=result.transition.event.value,
        token_version=result.token_version,
    )


@router.post("/verify", response_model=VerifyPickupResponse)
def verify_pickup(
    body: VerifyPickupRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> VerifyPickupResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])

    if body.qr_token:
        result = verify_pickup_by_qr(
            qr_token=body.qr_token.strip(),
            vendor_id=vendor_id,
            actor_id=current_user.id,
        )
        return _to_response(result)

    assert body.order_id is not None and body.pin is not None
    result = verify_pickup_by_pin(
        order_id=body.order_id.strip(),
        pin=body.pin.strip(),
        vendor_id=vendor_id,
        actor_id=current_user.id,
    )
    return _to_response(result)
