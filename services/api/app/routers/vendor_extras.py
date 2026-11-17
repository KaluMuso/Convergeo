"""Vendor: paid extras catalogue + requests (migration 20261117020000).

Payments are off: a request records interest (``vendor_extras_requests``) and
notifies admins in-app; no money is collected. Status changes only through the
guarded ``transition_vendor_extras_request()`` (history in
``vendor_extras_request_events``). Requests are per shop (the acting branch).

Every mutation: vendor role + shop ownership + strict Pydantic + an in-router
``STANDARD_WRITE`` rate limit keyed by the user.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import STANDARD_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.kyc.caps import _load_vendor_for_owner
from app.services.kyc.state_machine import ServiceRoleClient
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/vendor/extras", tags=["vendor-extras"])

EXTRA_COLUMNS = (
    "key, name, description, pricing, price_ngwee, price_max_ngwee, unit, "
    "price_is_placeholder, active, position"
)
REQUEST_COLUMNS = (
    "id, vendor_id, extra_key, quantity, note, status, quoted_price_ngwee, admin_note, "
    "decided_at, created_at, updated_at"
)
OPEN_STATUSES = ("requested", "quoted", "approved")


class ExtraOut(BaseModel):
    key: str
    name: str
    description: str
    pricing: Literal["fixed", "range", "pay_as_you_go"]
    price_ngwee: int | None = None
    price_max_ngwee: int | None = None
    unit: Literal["one_off", "per_month", "per_item"]
    price_is_placeholder: bool = False


class ExtraRequestOut(BaseModel):
    id: str
    extra_key: str
    quantity: int
    note: str | None = None
    status: str
    quoted_price_ngwee: int | None = None
    admin_note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ExtrasCatalogue(BaseModel):
    extras: list[ExtraOut]
    requests: list[ExtraRequestOut]


class ExtraRequestCreate(StrictModel):
    extra_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    quantity: int = Field(default=1, ge=1, le=10_000)
    note: str | None = Field(default=None, max_length=500)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _limit(client: Any, user_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=STANDARD_WRITE.scope,
        key=f"extras:{user_id}",
        window=STANDARD_WRITE.window,
        limit=STANDARD_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(retry_after=retry_after, message_key="vendor.extras.errors.rateLimited")


def extra_from_row(row: dict[str, Any]) -> ExtraOut:
    def _int(value: Any) -> int | None:
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

    return ExtraOut(
        key=str(row["key"]),
        name=str(row.get("name") or row["key"]),
        description=str(row.get("description") or ""),
        pricing=row.get("pricing") or "fixed",
        price_ngwee=_int(row.get("price_ngwee")),
        price_max_ngwee=_int(row.get("price_max_ngwee")),
        unit=row.get("unit") or "one_off",
        price_is_placeholder=row.get("price_is_placeholder") is True,
    )


def request_from_row(row: dict[str, Any]) -> ExtraRequestOut:
    quoted = row.get("quoted_price_ngwee")
    return ExtraRequestOut(
        id=str(row["id"]),
        extra_key=str(row["extra_key"]),
        quantity=int(row.get("quantity") or 1),
        note=row.get("note"),
        status=str(row.get("status") or "requested"),
        quoted_price_ngwee=int(quoted) if isinstance(quoted, int) else None,
        admin_note=row.get("admin_note"),
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def map_transition_error(exc: BaseException) -> AppError:
    message = str(getattr(exc, "message", "") or exc)
    for code, status, key in (
        ("extras_request_not_found", 404, "vendor.extras.errors.notFound"),
        ("extras_request_not_owner", 404, "vendor.extras.errors.notFound"),
        ("extras_invalid_transition", 409, "vendor.extras.errors.invalidTransition"),
        ("extras_quote_price_required", 422, "admin.extras.errors.quoteRequired"),
        ("extras_quote_price_unexpected", 422, "admin.extras.errors.quoteUnexpected"),
    ):
        if code in message:
            return AppError(
                code=code, message=code, http_status=status, details={"message_key": key}
            )
    raise exc


def _list_requests(client: Any, vendor_id: str) -> list[ExtraRequestOut]:
    rows = _rows(
        client.table("vendor_extras_requests")
        .select(REQUEST_COLUMNS)
        .eq("vendor_id", vendor_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    return [request_from_row(row) for row in rows]


@router.get("", response_model=ExtrasCatalogue)
async def list_extras(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ExtrasCatalogue:
    client: Any = service_client.client
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    extras = _rows(
        client.table("vendor_extras")
        .select(EXTRA_COLUMNS)
        .eq("active", True)
        .order("position")
        .execute()
    )
    return ExtrasCatalogue(
        extras=[extra_from_row(row) for row in extras],
        requests=_list_requests(client, str(vendor["id"])),
    )


@router.post("/requests", response_model=ExtraRequestOut, status_code=201)
async def request_extra(
    body: ExtraRequestCreate,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ExtraRequestOut:
    client: Any = service_client.client
    _limit(client, current_user.id)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])
    extra = _rows(
        client.table("vendor_extras")
        .select("key, active")
        .eq("key", body.extra_key)
        .eq("active", True)
        .execute()
    )
    if not extra:
        raise AppError(
            code="not_found",
            message="Extra not found",
            http_status=404,
            details={"message_key": "vendor.extras.errors.notFound"},
        )
    open_rows = _rows(
        client.table("vendor_extras_requests")
        .select("id")
        .eq("vendor_id", vendor_id)
        .eq("extra_key", body.extra_key)
        .in_("status", list(OPEN_STATUSES))
        .execute()
    )
    if open_rows:
        raise AppError(
            code="conflict",
            message="An open request for this extra already exists",
            http_status=409,
            details={"message_key": "vendor.extras.errors.alreadyRequested"},
        )
    note = body.note.strip() if body.note and body.note.strip() else None
    try:
        created = _rows(
            client.table("vendor_extras_requests")
            .insert(
                {
                    "vendor_id": vendor_id,
                    "extra_key": body.extra_key,
                    "requested_by": current_user.id,
                    "quantity": body.quantity,
                    "note": note,
                }
            )
            .execute()
        )
    except Exception as exc:
        if getattr(exc, "code", None) == "23505":
            raise AppError(
                code="conflict",
                message="An open request for this extra already exists",
                http_status=409,
                details={"message_key": "vendor.extras.errors.alreadyRequested"},
            ) from exc
        raise
    if not created:
        raise AppError(code="internal_error", message="Request not recorded", http_status=500)
    return request_from_row(created[0])


def _vendor_transition(
    service_client: ServiceRoleClient,
    current_user: CurrentUser,
    request_id: UUID,
    to_status: str,
) -> ExtraRequestOut:
    client: Any = service_client.client
    _limit(client, current_user.id)
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    rows = _rows(
        client.table("vendor_extras_requests")
        .select(REQUEST_COLUMNS)
        .eq("id", str(request_id))
        .eq("vendor_id", str(vendor["id"]))
        .execute()
    )
    if not rows:
        raise AppError(
            code="not_found",
            message="Request not found",
            http_status=404,
            details={"message_key": "vendor.extras.errors.notFound"},
        )
    try:
        client.rpc(
            "transition_vendor_extras_request",
            {
                "p_request_id": str(request_id),
                "p_to": to_status,
                "p_actor": current_user.id,
                "p_actor_role": "vendor",
                "p_note": None,
                "p_quoted_price_ngwee": None,
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001 — DB refusal -> stable error
        raise map_transition_error(exc) from exc
    refreshed = _rows(
        client.table("vendor_extras_requests")
        .select(REQUEST_COLUMNS)
        .eq("id", str(request_id))
        .execute()
    )
    return request_from_row(refreshed[0] if refreshed else rows[0])


@router.post("/requests/{request_id}/cancel", response_model=ExtraRequestOut)
async def cancel_extra_request(
    request_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ExtraRequestOut:
    return _vendor_transition(service_client, current_user, request_id, "cancelled")


@router.post("/requests/{request_id}/accept", response_model=ExtraRequestOut)
async def accept_extra_quote(
    request_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ExtraRequestOut:
    return _vendor_transition(service_client, current_user, request_id, "approved")
