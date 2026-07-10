"""COD collection confirmation — vendor and admin scoped."""

from __future__ import annotations

from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.orders.state import ActorRole, OrderTransitionError
from app.services.payments.cod import (
    CodError,
    confirm_cod_collection,
    refuse_cod_collection,
)
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(tags=["cod"])


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


class CodNoteRequest(StrictModel):
    note: str = Field(min_length=1, max_length=2000)


class CodCollectionResponse(StrictModel):
    order_id: str
    collectable_ngwee: int
    commission_ngwee: int
    net_vendor_ngwee: int
    transaction_ids: list[str]
    idempotent_replay: bool


class CodRefusalResponse(StrictModel):
    order_id: str
    collectable_ngwee: int
    reversal_transaction_id: str
    from_status: str
    to_status: str
    idempotent_replay: bool


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
        )
    return row


def _load_order_vendor_id(service_client: _ServiceRoleClient, order_id: str) -> str:
    response = (
        service_client.client.table("orders")
        .select("id, vendor_id")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    vendor_id = row.get("vendor_id")
    if not isinstance(vendor_id, str):
        raise AppError(
            code="internal_error",
            message="Order vendor_id missing",
            http_status=500,
        )
    return vendor_id


def _assert_vendor_owns_order(*, vendor_id: str, order_vendor_id: str) -> None:
    if vendor_id != order_vendor_id:
        raise AppError(
            code="forbidden",
            message="Vendor may only act on their own orders",
            http_status=403,
        )


def _map_cod_error(exc: CodError) -> AppError:
    return AppError(
        code=exc.code,
        message=exc.message,
        http_status=exc.http_status,
        details=exc.details,
    )


vendor_router = APIRouter(prefix="/vendor/orders", tags=["vendor-cod"])


@vendor_router.post("/{order_id}/cod/confirm-collection", response_model=CodCollectionResponse)
def vendor_confirm_cod_collection(
    order_id: str,
    body: CodNoteRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CodCollectionResponse:
    vendor = _load_vendor_for_owner(service_client, user.id)
    order_vendor_id = _load_order_vendor_id(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_vendor_id=order_vendor_id)

    try:
        result = confirm_cod_collection(
            order_id=order_id,
            actor_id=user.id,
            note=body.note,
        )
    except CodError as exc:
        raise _map_cod_error(exc) from exc
    except OrderTransitionError as exc:
        raise AppError(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            details=exc.details,
        ) from exc

    return CodCollectionResponse(
        order_id=result.order_id,
        collectable_ngwee=result.collectable_ngwee,
        commission_ngwee=result.commission_ngwee,
        net_vendor_ngwee=result.net_vendor_ngwee,
        transaction_ids=list(result.transaction_ids),
        idempotent_replay=not result.created,
    )


@vendor_router.post("/{order_id}/cod/refuse-collection", response_model=CodRefusalResponse)
def vendor_refuse_cod_collection(
    order_id: str,
    body: CodNoteRequest,
    user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> CodRefusalResponse:
    vendor = _load_vendor_for_owner(service_client, user.id)
    order_vendor_id = _load_order_vendor_id(service_client, order_id)
    _assert_vendor_owns_order(vendor_id=str(vendor["id"]), order_vendor_id=order_vendor_id)

    try:
        result = refuse_cod_collection(
            order_id=order_id,
            actor_role=ActorRole.VENDOR,
            actor_id=user.id,
            note=body.note,
        )
    except CodError as exc:
        raise _map_cod_error(exc) from exc
    except OrderTransitionError as exc:
        raise AppError(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            details=exc.details,
        ) from exc

    return CodRefusalResponse(
        order_id=result.order_id,
        collectable_ngwee=result.collectable_ngwee,
        reversal_transaction_id=result.reversal_transaction_id,
        from_status=result.from_status,
        to_status=result.to_status,
        idempotent_replay=not result.created,
    )


admin_router = APIRouter(prefix="/admin/orders", tags=["admin-cod"])


@admin_router.post("/{order_id}/cod/confirm-collection", response_model=CodCollectionResponse)
def admin_confirm_cod_collection(
    order_id: str,
    body: CodNoteRequest,
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> CodCollectionResponse:
    _ = user
    try:
        result = confirm_cod_collection(
            order_id=order_id,
            actor_id=user.id,
            note=body.note,
        )
    except CodError as exc:
        raise _map_cod_error(exc) from exc
    except OrderTransitionError as exc:
        raise AppError(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            details=exc.details,
        ) from exc

    return CodCollectionResponse(
        order_id=result.order_id,
        collectable_ngwee=result.collectable_ngwee,
        commission_ngwee=result.commission_ngwee,
        net_vendor_ngwee=result.net_vendor_ngwee,
        transaction_ids=list(result.transaction_ids),
        idempotent_replay=not result.created,
    )


@admin_router.post("/{order_id}/cod/refuse-collection", response_model=CodRefusalResponse)
def admin_refuse_cod_collection(
    order_id: str,
    body: CodNoteRequest,
    user: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> CodRefusalResponse:
    try:
        result = refuse_cod_collection(
            order_id=order_id,
            actor_role=ActorRole.ADMIN,
            actor_id=user.id,
            note=body.note,
        )
    except CodError as exc:
        raise _map_cod_error(exc) from exc
    except OrderTransitionError as exc:
        raise AppError(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            details=exc.details,
        ) from exc

    return CodRefusalResponse(
        order_id=result.order_id,
        collectable_ngwee=result.collectable_ngwee,
        reversal_transaction_id=result.reversal_transaction_id,
        from_status=result.from_status,
        to_status=result.to_status,
        idempotent_replay=not result.created,
    )


router.include_router(vendor_router)
router.include_router(admin_router)
