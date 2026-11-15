"""Vendor/admin offer management helpers (W8): ownership, abuse caps, preview."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.errors import AppError
from app.schemas.offers import (
    OfferItemOut,
    OfferOut,
    OfferPreviewLine,
    OfferPreviewResponse,
    OfferWriteRequest,
)
from app.services.offers.engine import (
    OfferDef,
    OfferItemDef,
    PricingLine,
    price_cart,
)
from app.services.offers.store import (
    ITEM_COLUMNS,
    OFFER_COLUMNS,
    item_ref,
    max_discount_pct,
    offer_is_live,
    offers_enabled,
)

INACTIVE_LISTING_STATUSES = frozenset({"removed", "archived", "rejected"})


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def require_bundles_enabled(client: Any) -> None:
    if not offers_enabled(client):
        raise AppError(
            code="offers.disabled",
            message="Offers are not available yet",
            http_status=404,
            details={"message_key": "vendor.offers.errors.disabled"},
        )


def offer_not_found() -> AppError:
    return AppError(
        code="offers.not_found",
        message="Offer not found",
        http_status=404,
        details={"message_key": "vendor.offers.errors.notFound"},
    )


def listing_title(row: dict[str, Any]) -> str | None:
    override = row.get("title_override")
    if isinstance(override, str) and override.strip():
        return override.strip()
    product = row.get("products")
    if isinstance(product, dict):
        name = product.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def load_targets(client: Any, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """ref_id -> {vendor_id, title, unit_price_ngwee, available, kind} for every item."""
    out: dict[str, dict[str, Any]] = {}
    listing_ids = sorted({str(i["ref"]) for i in items if i["kind"] == "product"})
    service_ids = sorted({str(i["ref"]) for i in items if i["kind"] == "service"})
    event_ids = sorted({str(i["ref"]) for i in items if i["kind"] == "event"})
    if listing_ids:
        for row in _rows(
            client.table("vendor_listings")
            .select("id, vendor_id, price_ngwee, status, title_override, products(name)")
            .in_("id", listing_ids)
            .execute()
        ):
            out[str(row["id"])] = {
                "kind": "product",
                "vendor_id": str(row.get("vendor_id")),
                "title": listing_title(row),
                "unit_price_ngwee": int(row["price_ngwee"])
                if isinstance(row.get("price_ngwee"), int)
                else None,
                "available": str(row.get("status")) not in INACTIVE_LISTING_STATUSES,
            }
    if service_ids:
        for row in _rows(
            client.table("services")
            .select("id, vendor_id, title, from_price_ngwee, status")
            .in_("id", service_ids)
            .execute()
        ):
            out[str(row["id"])] = {
                "kind": "service",
                "vendor_id": str(row.get("vendor_id")),
                "title": row.get("title"),
                "unit_price_ngwee": row.get("from_price_ngwee")
                if isinstance(row.get("from_price_ngwee"), int)
                else None,
                "available": row.get("status") != "paused",
            }
    if event_ids:
        for row in _rows(
            client.table("events")
            .select("id, organiser_vendor_id, title, status")
            .in_("id", event_ids)
            .execute()
        ):
            out[str(row["id"])] = {
                "kind": "event",
                "vendor_id": str(row.get("organiser_vendor_id")),
                "title": row.get("title"),
                "unit_price_ngwee": None,
                "available": row.get("status") in ("draft", "published"),
            }
    return out


def assert_items_owned(
    targets: dict[str, dict[str, Any]], body: OfferWriteRequest, vendor_id: str
) -> None:
    for item in body.items:
        target = targets.get(item.ref_id.lower()) or targets.get(item.ref_id)
        if target is None or target["kind"] != item.item_kind:
            raise AppError(
                code="offers.item_not_found",
                message="Offer item not found",
                http_status=404,
                details={"message_key": "vendor.offers.errors.itemNotFound", "ref_id": item.ref_id},
            )
        if target["vendor_id"] != vendor_id:
            raise AppError(
                code="offers.item_forbidden",
                message="Offer items must be your own listings, services or events",
                http_status=403,
                details={
                    "message_key": "vendor.offers.errors.itemForbidden",
                    "ref_id": item.ref_id,
                },
            )
        if not target["available"]:
            raise AppError(
                code="offers.item_unavailable",
                message="Offer item is not available",
                http_status=422,
                details={
                    "message_key": "vendor.offers.errors.itemUnavailable",
                    "ref_id": item.ref_id,
                },
            )


def offer_def_from_request(
    body: OfferWriteRequest,
    *,
    vendor_id: str,
    targets: dict[str, dict[str, Any]],
    offer_id: str = "00000000-0000-4000-8000-000000000000",
) -> OfferDef:
    reward = next((i for i in body.items if i.role == "reward"), None)
    reward_target = targets.get(reward.ref_id.lower()) if reward is not None else None
    return OfferDef(
        id=offer_id,
        vendor_id=vendor_id,
        offer_type=body.offer_type,
        title=body.title.strip(),
        items=tuple(
            OfferItemDef(role=i.role, item_kind=i.item_kind, ref_id=i.ref_id.lower(), qty=i.qty)
            for i in body.items
        ),
        buy_qty=body.buy_qty,
        get_qty=body.get_qty,
        bundle_pricing=body.bundle_pricing,
        addon_percent_off=body.addon_percent_off,
        bundle_price_ngwee=body.bundle_price_ngwee,
        buy_n=body.buy_n,
        pay_m=body.pay_m,
        gift_available=body.gift_stock_total,
        max_applications_per_order=body.max_applications_per_order,
        reward_unit_price_ngwee=reward_target.get("unit_price_ngwee") if reward_target else None,
        reward_title=reward_target.get("title") if reward_target else None,
    )


def assert_within_discount_cap(
    body: OfferWriteRequest, targets: dict[str, dict[str, Any]], cap_pct: int
) -> None:
    """Admin abuse cap on the discount (percent of list value)."""

    def fail(field: str) -> AppError:
        return AppError(
            code="offers.discount_too_large",
            message="Offer discount exceeds the allowed maximum",
            http_status=422,
            details={
                "message_key": "vendor.offers.errors.discountTooLarge",
                "field": field,
                "max_discount_pct": cap_pct,
            },
        )

    if body.offer_type == "bundle":
        if body.bundle_pricing == "addon_percent_off" and body.addon_percent_off is not None:
            if body.addon_percent_off > cap_pct:
                raise fail("addon_percent_off")
        elif body.bundle_price_ngwee is not None:
            list_total = 0
            for item in body.items:
                price = targets[item.ref_id.lower()]["unit_price_ngwee"] or 0
                list_total += price * item.qty
            if body.bundle_price_ngwee >= list_total:
                raise AppError(
                    code="offers.no_saving",
                    message="Bundle price must be below the items' total price",
                    http_status=422,
                    details={
                        "message_key": "vendor.offers.errors.noSaving",
                        "field": "bundle_price_ngwee",
                        "list_total_ngwee": list_total,
                    },
                )
            if (list_total - body.bundle_price_ngwee) * 100 > list_total * cap_pct:
                raise fail("bundle_price_ngwee")
    elif body.offer_type == "buy_n_pay_m" and body.buy_n and body.pay_m:
        if (body.buy_n - body.pay_m) * 100 > body.buy_n * cap_pct:
            raise fail("pay_m")


def preview_offer(
    body: OfferWriteRequest,
    *,
    vendor_id: str,
    targets: dict[str, dict[str, Any]],
    cap_pct: int,
) -> OfferPreviewResponse:
    """What a customer pays for the smallest basket that triggers the offer once."""
    offer = offer_def_from_request(body, vendor_id=vendor_id, targets=targets)
    basket: list[tuple[str, str, int]] = []  # (ref, role, qty)
    if body.offer_type == "bundle":
        basket = [(i.ref_id.lower(), i.role, i.qty) for i in body.items]
    elif body.offer_type == "buy_n_pay_m":
        first = next(i for i in body.items if i.role == "eligible")
        basket = [(first.ref_id.lower(), "eligible", body.buy_n or 1)]
    else:
        first = next(i for i in body.items if i.role == "trigger")
        need = (body.buy_qty or 1) if body.offer_type == "bxgy" else 1
        basket = [(first.ref_id.lower(), "trigger", need * first.qty)]
    lines: list[PricingLine] = []
    roles: dict[str, str] = {}
    for index, (ref, role, qty) in enumerate(basket):
        price = targets.get(ref, {}).get("unit_price_ngwee")
        target_kind = targets.get(ref, {}).get("kind")
        if not isinstance(price, int) or price <= 0 or target_kind != "product":
            continue
        key = f"preview-{index}"
        roles[key] = role
        lines.append(
            PricingLine(
                key=key, listing_id=ref, vendor_id=vendor_id, qty=qty, unit_price_ngwee=price
            )
        )
    if not lines:
        return OfferPreviewResponse(
            applies=False,
            list_total_ngwee=0,
            pay_ngwee=0,
            savings_ngwee=0,
            gift_qty=0,
            gift_value_ngwee=0,
            lines=[],
        )
    priced = price_cart(lines, [offer], max_discount_pct=cap_pct)
    preview_lines = [
        OfferPreviewLine(
            ref_id=line.listing_id,
            role=roles[line.key],
            qty=line.qty,
            list_total_ngwee=priced.lines[line.key].list_total_ngwee,
            final_total_ngwee=priced.lines[line.key].final_total_ngwee,
        )
        for line in lines
    ]
    list_total = sum(p.list_total_ngwee for p in preview_lines)
    pay = sum(p.final_total_ngwee for p in preview_lines)
    gift_qty = sum(g.qty for g in priced.gifts)
    return OfferPreviewResponse(
        applies=bool(priced.applications),
        list_total_ngwee=list_total,
        pay_ngwee=pay,
        savings_ngwee=list_total - pay,
        gift_qty=gift_qty,
        gift_value_ngwee=priced.gift_value_ngwee,
        lines=preview_lines,
    )


def load_offer_rows(
    client: Any, *, vendor_id: str | None = None, offer_id: str | None = None
) -> list[dict[str, Any]]:
    query = client.table("offers").select(OFFER_COLUMNS + ", admin_note, created_at, updated_at")
    if vendor_id is not None:
        query = query.eq("vendor_id", vendor_id)
    if offer_id is not None:
        query = query.eq("id", offer_id)
    rows = _rows(query.order("created_at", desc=True).execute())
    return rows


def load_items_for(client: Any, offer_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not offer_ids:
        return {}
    by_offer: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(
        client.table("offer_items")
        .select(ITEM_COLUMNS)
        .in_("offer_id", offer_ids)
        .order("sort_order")
        .execute()
    ):
        by_offer.setdefault(str(row.get("offer_id")), []).append(row)
    return by_offer


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def to_offer_out(
    row: dict[str, Any],
    items: list[dict[str, Any]],
    targets: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> OfferOut:
    moment = now or datetime.now(UTC)
    total = row.get("gift_stock_total")
    reserved = int(row.get("gift_stock_reserved") or 0)
    item_outs: list[OfferItemOut] = []
    for item in items:
        ref = item_ref(item)
        if ref is None:
            continue
        target = targets.get(ref, {})
        item_outs.append(
            OfferItemOut(
                role=str(item.get("role")),
                item_kind=str(item.get("item_kind")),
                ref_id=ref,
                qty=int(item.get("qty") or 1),
                title=target.get("title"),
                unit_price_ngwee=target.get("unit_price_ngwee"),
                available=bool(target.get("available", False)),
            )
        )
    return OfferOut(
        id=str(row["id"]),
        vendor_id=str(row["vendor_id"]),
        offer_type=str(row["offer_type"]),
        title=str(row.get("title") or ""),
        status=row.get("status") or "draft",
        starts_at=_parse_dt(row.get("starts_at")),
        ends_at=_parse_dt(row.get("ends_at")),
        buy_qty=row.get("buy_qty"),
        get_qty=row.get("get_qty"),
        bundle_pricing=row.get("bundle_pricing"),
        addon_percent_off=row.get("addon_percent_off"),
        bundle_price_ngwee=row.get("bundle_price_ngwee"),
        buy_n=row.get("buy_n"),
        pay_m=row.get("pay_m"),
        gift_stock_total=total if isinstance(total, int) else None,
        gift_stock_reserved=reserved,
        gift_stock_available=max(0, total - reserved) if isinstance(total, int) else None,
        max_applications_per_order=int(row.get("max_applications_per_order") or 1),
        per_customer_limit=row.get("per_customer_limit"),
        paused_by_admin=bool(row.get("paused_by_admin")),
        live=offer_is_live(row, moment),
        cart_applicable=all(i.item_kind == "product" for i in item_outs),
        items=item_outs,
        created_at=_parse_dt(row.get("created_at")),
        updated_at=_parse_dt(row.get("updated_at")),
    )


def targets_for_item_rows(
    client: Any, item_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    refs = [
        {"kind": str(item.get("item_kind")), "ref": item_ref(item)}
        for item in item_rows
        if item_ref(item) is not None
    ]
    return load_targets(client, refs)


def cap_pct(client: Any) -> int:
    return max_discount_pct(client)
