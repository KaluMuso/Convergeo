from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.moderation.prohibited import screen_listing
from app.services.stock.revalidate import CartLineSnapshot, RevalidateResult, revalidate_lines
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator, model_validator

router = APIRouter(prefix="/vendor/listings", tags=["vendor-listings-manage"])

ListingCondition = Literal["new", "refurbished"]
StockMode = Literal["tracked", "always_available"]
ListingStatus = Literal["draft", "active", "paused"]
EDITABLE_LISTING_STATUSES = frozenset({"draft", "active", "paused"})
OPEN_ORDER_STATUSES = frozenset(
    {"placed", "confirmed", "processing", "ready", "shipped", "delivered"}
)


class PriceTierInput(StrictModel):
    min_qty: int = Field(ge=1)
    price_ngwee: NgweeInt


class ListingSummary(StrictModel):
    id: str
    title: str
    price_ngwee: int
    compare_at_ngwee: int | None = None
    condition: ListingCondition
    stock_mode: StockMode
    stock_qty: int | None
    wholesale: bool
    price_tiers: list[dict[str, int]] | None = None
    moq: int
    returnable: bool
    return_window_hours: int | None
    status: str
    product_id: str | None


class ListingUpdateRequest(StrictModel):
    price_ngwee: NgweeInt | None = None
    compare_at_ngwee: NgweeInt | None = None
    condition: ListingCondition | None = None
    stock_mode: StockMode | None = None
    stock_qty: int | None = Field(default=None, ge=0)
    wholesale: bool | None = None
    price_tiers: list[PriceTierInput] | None = None
    moq: int | None = Field(default=None, ge=1)
    returnable: bool | None = None
    return_window_hours: int | None = None
    status: ListingStatus | None = None

    @field_validator("price_ngwee")
    @classmethod
    def price_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            msg = "price_ngwee must be greater than zero"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_return_window(self) -> ListingUpdateRequest:
        if self.returnable is True and self.return_window_hours is None:
            raise ValueError("return_window_hours is required when returnable is true")
        # When both are supplied together, enforce a positive discount here for a
        # friendly error; the compare-at-only case is checked in _apply_listing_update
        # against the stored price (and the DB check constraint is the backstop).
        if (
            self.compare_at_ngwee is not None
            and self.price_ngwee is not None
            and self.compare_at_ngwee <= self.price_ngwee
        ):
            raise ValueError("compare_at_ngwee must be greater than price_ngwee")
        return self


class StockAdjustRequest(StrictModel):
    delta: int = Field(ge=-999_999, le=999_999)


class CartRevalidationSummary(StrictModel):
    triggered: bool
    affected_carts: int
    has_changes: bool


class ListingUpdateResponse(StrictModel):
    listing: ListingSummary
    cart_revalidation: CartRevalidationSummary | None = None


class ListingDeleteResponse(StrictModel):
    listing_id: str
    deleted: bool
    paused_instead: bool
    status: str
    message_key: str


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _load_vendor_for_owner(
    service_client: ServiceRoleClient,
    owner_user_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendors")
        .select("id, owner_user_id, status, kyc_tier")
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


def _validate_price_tiers_ordered(tiers: list[PriceTierInput]) -> None:
    if not tiers:
        return
    ordered = sorted(tiers, key=lambda tier: tier.min_qty)
    prev_qty = 0
    prev_price: int | None = None
    for tier in ordered:
        if tier.min_qty <= prev_qty:
            raise AppError(
                code="invalid_price_tiers",
                message="Price tiers must have strictly ascending min_qty",
                http_status=422,
                details={"message_key": "vendor.listings.errors.invalid_tiers"},
            )
        if prev_price is not None and tier.price_ngwee >= prev_price:
            raise AppError(
                code="invalid_price_tiers",
                message="Price tiers must have strictly descending unit prices",
                http_status=422,
                details={"message_key": "vendor.listings.errors.invalid_tiers"},
            )
        prev_qty = tier.min_qty
        prev_price = tier.price_ngwee


def _serialize_price_tiers(tiers: list[PriceTierInput] | None) -> list[dict[str, int]] | None:
    if tiers is None:
        return None
    if not tiers:
        return []
    return [{"min_qty": tier.min_qty, "price_ngwee": tier.price_ngwee} for tier in tiers]


def _listing_title(row: dict[str, Any]) -> str:
    title_override = row.get("title_override")
    if isinstance(title_override, str) and title_override.strip():
        return title_override.strip()
    products = row.get("products")
    if isinstance(products, dict):
        name = products.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "Listing"


def _to_listing_summary(row: dict[str, Any]) -> ListingSummary:
    return ListingSummary(
        id=str(row["id"]),
        title=_listing_title(row),
        price_ngwee=int(row["price_ngwee"]),
        compare_at_ngwee=(
            int(row["compare_at_ngwee"]) if row.get("compare_at_ngwee") is not None else None
        ),
        condition=str(row["condition"]),  # type: ignore[arg-type]
        stock_mode=str(row["stock_mode"]),  # type: ignore[arg-type]
        stock_qty=int(row["stock_qty"]) if row.get("stock_qty") is not None else None,
        wholesale=bool(row.get("wholesale")),
        price_tiers=row.get("price_tiers") if isinstance(row.get("price_tiers"), list) else None,
        moq=int(row.get("moq") or 1),
        returnable=bool(row.get("returnable")),
        return_window_hours=(
            int(row["return_window_hours"]) if row.get("return_window_hours") is not None else None
        ),
        status=str(row["status"]),
        product_id=str(row["product_id"]) if row.get("product_id") else None,
    )


def _load_listing(
    service_client: ServiceRoleClient,
    listing_id: str,
) -> dict[str, Any]:
    response = (
        service_client.client.table("vendor_listings")
        .select(
            "id, vendor_id, product_id, title_override, price_ngwee, compare_at_ngwee, "
            "condition, stock_mode, stock_qty, wholesale, price_tiers, moq, returnable, "
            "return_window_hours, status, products(name)"
        )
        .eq("id", listing_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(
            code="not_found",
            message="Listing not found",
            http_status=404,
            details={"listing_id": listing_id},
        )
    return row


def _assert_listing_owned_by_vendor(
    listing: dict[str, Any],
    vendor_id: str,
    *,
    listing_id: str,
) -> None:
    if str(listing.get("vendor_id")) != vendor_id:
        raise AppError(
            code="forbidden",
            message="Listing does not belong to the authenticated vendor",
            http_status=403,
            details={"listing_id": listing_id, "vendor_id": vendor_id},
        )


def _assert_listing_editable(listing: dict[str, Any], *, listing_id: str) -> None:
    status = str(listing.get("status", ""))
    if status not in EDITABLE_LISTING_STATUSES:
        raise AppError(
            code="listing_not_editable",
            message="Listing status does not allow edits",
            http_status=409,
            details={"listing_id": listing_id, "status": status},
        )


def _listing_has_open_orders(service_client: ServiceRoleClient, listing_id: str) -> bool:
    item_links = _rows(
        service_client.client.table("order_item_products")
        .select("order_item_id, order_items(order_id)")
        .eq("listing_id", listing_id)
        .execute()
    )
    order_ids: list[str] = []
    for link in item_links:
        order_items = link.get("order_items")
        if isinstance(order_items, dict):
            order_id = order_items.get("order_id")
            if order_id is not None:
                order_ids.append(str(order_id))
    if not order_ids:
        return False

    orders = _rows(
        service_client.client.table("orders")
        .select("id, status")
        .in_("id", sorted(set(order_ids)))
        .in_("status", sorted(OPEN_ORDER_STATUSES))
        .limit(1)
        .execute()
    )
    return bool(orders)


def _fetch_cart_lines_for_listing(
    service_client: ServiceRoleClient,
    listing_id: str,
) -> list[CartLineSnapshot]:
    rows = _rows(
        service_client.client.table("cart_items")
        .select("listing_id, qty, unit_price_ngwee, carts!inner(status)")
        .eq("listing_id", listing_id)
        .eq("carts.status", "active")
        .execute()
    )
    lines: list[CartLineSnapshot] = []
    for row in rows:
        carts = row.get("carts")
        if isinstance(carts, dict) and carts.get("status") != "active":
            continue
        lines.append(
            CartLineSnapshot(
                listing_id=str(row["listing_id"]),
                qty=int(row["qty"]),
                unit_price_ngwee=int(row["unit_price_ngwee"]),
            )
        )
    return lines


def _trigger_cart_revalidation(
    service_client: ServiceRoleClient,
    listing_id: str,
) -> CartRevalidationSummary:
    lines = _fetch_cart_lines_for_listing(service_client, listing_id)
    if not lines:
        return CartRevalidationSummary(triggered=True, affected_carts=0, has_changes=False)

    result: RevalidateResult = revalidate_lines(lines)
    return CartRevalidationSummary(
        triggered=True,
        affected_carts=len(lines),
        has_changes=result.has_changes,
    )


def _apply_listing_update(
    service_client: ServiceRoleClient,
    listing_id: str,
    listing: dict[str, Any],
    body: ListingUpdateRequest,
    *,
    vendor: dict[str, Any],
) -> tuple[dict[str, Any], CartRevalidationSummary | None]:
    _assert_listing_editable(listing, listing_id=listing_id)

    if body.price_tiers is not None:
        _validate_price_tiers_ordered(body.price_tiers)

    wholesale = body.wholesale if body.wholesale is not None else bool(listing.get("wholesale"))
    if wholesale:
        from app.services.kyc.eligibility import (
            require_wholesale_eligible,
            resolve_vendor_eligibility,
        )

        eligibility = resolve_vendor_eligibility(
            service_client,
            str(vendor["id"]),
            vendor_row=vendor,
        )
        require_wholesale_eligible(eligibility)

    stock_mode = body.stock_mode or str(listing.get("stock_mode"))
    stock_qty = body.stock_qty if body.stock_qty is not None else listing.get("stock_qty")
    if stock_mode == "tracked" and stock_qty is None:
        raise AppError(
            code="validation_error",
            message="stock_qty is required when stock_mode is tracked",
            http_status=422,
            details={"message_key": "vendor.listings.manage.errors.stock_qty_required"},
        )

    returnable = body.returnable if body.returnable is not None else bool(listing.get("returnable"))
    return_window = (
        body.return_window_hours
        if body.return_window_hours is not None
        else listing.get("return_window_hours")
    )
    if returnable and return_window is None:
        raise AppError(
            code="validation_error",
            message="return_window_hours is required when returnable is true",
            http_status=422,
            details={"message_key": "vendor.listings.manage.errors.return_window_required"},
        )

    update_payload: dict[str, Any] = {}
    if body.price_ngwee is not None:
        update_payload["price_ngwee"] = body.price_ngwee
    # model_fields_set (not `is not None`) so an explicit null clears the
    # compare-at price — i.e. ends a sale. Positive-discount is enforced below
    # and by the DB check constraint.
    if "compare_at_ngwee" in body.model_fields_set:
        update_payload["compare_at_ngwee"] = body.compare_at_ngwee
    if body.condition is not None:
        update_payload["condition"] = body.condition
    if body.stock_mode is not None:
        update_payload["stock_mode"] = body.stock_mode
    if body.stock_qty is not None:
        update_payload["stock_qty"] = body.stock_qty
    if body.wholesale is not None:
        update_payload["wholesale"] = body.wholesale
    if body.price_tiers is not None:
        update_payload["price_tiers"] = _serialize_price_tiers(body.price_tiers)
    if body.moq is not None:
        update_payload["moq"] = body.moq
    if body.returnable is not None:
        update_payload["returnable"] = body.returnable
    if body.return_window_hours is not None:
        update_payload["return_window_hours"] = body.return_window_hours
    if body.status is not None:
        update_payload["status"] = body.status

    if not update_payload:
        return listing, None

    old_price = int(listing["price_ngwee"])
    # Compare-at set on its own must still exceed the effective price (the new
    # price when it's changing, else the stored one) — a friendly 422 rather
    # than a raw DB constraint violation.
    new_compare_at = update_payload.get("compare_at_ngwee")
    if new_compare_at is not None:
        effective_price = int(update_payload.get("price_ngwee", old_price))
        if int(new_compare_at) <= effective_price:
            raise AppError(
                code="invalid_compare_at",
                message="compare_at_ngwee must be greater than price_ngwee",
                http_status=422,
                details={"message_key": "vendor.listings.errors.submitFailed"},
            )
    price_changed = (
        body.price_ngwee is not None and int(body.price_ngwee) != old_price
    ) or body.price_tiers is not None

    response = (
        service_client.client.table("vendor_listings")
        .update(update_payload)
        .eq("id", listing_id)
        .execute()
    )
    updated = _single_row(response) or {**listing, **update_payload}
    revalidation: CartRevalidationSummary | None = None
    if price_changed:
        revalidation = _trigger_cart_revalidation(service_client, listing_id)
    return updated, revalidation


@router.get("", response_model=list[ListingSummary])
async def list_vendor_listings(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> list[ListingSummary]:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    vendor_id = str(vendor["id"])

    response = (
        service_client.client.table("vendor_listings")
        .select(
            "id, vendor_id, product_id, title_override, price_ngwee, condition, "
            "stock_mode, stock_qty, wholesale, price_tiers, moq, returnable, return_window_hours, "
            "status, products(name)"
        )
        .eq("vendor_id", vendor_id)
        .neq("status", "removed")
        .order("updated_at", desc=True)
        .execute()
    )
    return [_to_listing_summary(row) for row in _rows(response)]


@router.get("/{listing_id}", response_model=ListingSummary)
async def get_vendor_listing(
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingSummary:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    listing = _load_listing(service_client, listing_id)
    _assert_listing_owned_by_vendor(listing, str(vendor["id"]), listing_id=listing_id)
    return _to_listing_summary(listing)


@router.patch("/{listing_id}", response_model=ListingUpdateResponse)
async def update_vendor_listing(
    listing_id: str,
    body: ListingUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingUpdateResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    listing = _load_listing(service_client, listing_id)
    _assert_listing_owned_by_vendor(listing, str(vendor["id"]), listing_id=listing_id)

    guard = screen_listing(title=_listing_title(listing))
    if not guard.allowed:
        raise AppError(
            code="prohibited_listing",
            message="Listing contains a prohibited category or keyword",
            http_status=422,
            details={
                "message_key": "vendor.listings.errors.submitFailed",
                "reason": guard.reason,
                "matched": guard.matched,
            },
        )

    updated, revalidation = _apply_listing_update(
        service_client,
        listing_id,
        listing,
        body,
        vendor=vendor,
    )
    refreshed = _load_listing(service_client, listing_id)
    return ListingUpdateResponse(
        listing=_to_listing_summary(refreshed if refreshed else updated),
        cart_revalidation=revalidation,
    )


@router.patch("/{listing_id}/stock", response_model=ListingUpdateResponse)
async def adjust_listing_stock(
    listing_id: str,
    body: StockAdjustRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingUpdateResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    listing = _load_listing(service_client, listing_id)
    _assert_listing_owned_by_vendor(listing, str(vendor["id"]), listing_id=listing_id)
    _assert_listing_editable(listing, listing_id=listing_id)

    if str(listing.get("stock_mode")) != "tracked":
        raise AppError(
            code="validation_error",
            message="Stock adjustments apply only to tracked listings",
            http_status=422,
            details={"message_key": "vendor.listings.manage.errors.stock_not_tracked"},
        )

    current_qty = int(listing.get("stock_qty") or 0)
    new_qty = max(current_qty + body.delta, 0)
    update_body = ListingUpdateRequest(stock_qty=new_qty)
    updated, revalidation = _apply_listing_update(
        service_client,
        listing_id,
        listing,
        update_body,
        vendor=vendor,
    )
    refreshed = _load_listing(service_client, listing_id)
    return ListingUpdateResponse(
        listing=_to_listing_summary(refreshed if refreshed else updated),
        cart_revalidation=revalidation,
    )


@router.post("/{listing_id}/pause", response_model=ListingUpdateResponse)
async def pause_vendor_listing(
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingUpdateResponse:
    return await update_vendor_listing(
        listing_id,
        ListingUpdateRequest(status="paused"),
        current_user,
        service_client,
    )


@router.post("/{listing_id}/unpause", response_model=ListingUpdateResponse)
async def unpause_vendor_listing(
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingUpdateResponse:
    return await update_vendor_listing(
        listing_id,
        ListingUpdateRequest(status="active"),
        current_user,
        service_client,
    )


@router.delete("/{listing_id}", response_model=ListingDeleteResponse)
async def delete_vendor_listing(
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> ListingDeleteResponse:
    vendor = _load_vendor_for_owner(service_client, current_user.id)
    listing = _load_listing(service_client, listing_id)
    _assert_listing_owned_by_vendor(listing, str(vendor["id"]), listing_id=listing_id)

    if _listing_has_open_orders(service_client, listing_id):
        response = (
            service_client.client.table("vendor_listings")
            .update({"status": "paused"})
            .eq("id", listing_id)
            .execute()
        )
        updated = _single_row(response)
        status = str(updated.get("status", "paused")) if updated else "paused"
        return ListingDeleteResponse(
            listing_id=listing_id,
            deleted=False,
            paused_instead=True,
            status=status,
            message_key="vendor.listings.manage.delete.paused_instead",
        )

    response = (
        service_client.client.table("vendor_listings")
        .update({"status": "removed"})
        .eq("id", listing_id)
        .execute()
    )
    updated = _single_row(response)
    status = str(updated.get("status", "removed")) if updated else "removed"
    return ListingDeleteResponse(
        listing_id=listing_id,
        deleted=True,
        paused_instead=False,
        status=status,
        message_key="vendor.listings.manage.delete.removed",
    )
