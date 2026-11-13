"""Who pays for delivery, per vendor group (logistics phase 1, founder decision 1).

Rules, in order, for every vendor group the customer chose to have delivered:

1. **Vendor free delivery.** The vendor marked every listing in the group
   "free delivery", or offers free delivery on everything. The customer pays
   nothing. The vendor bears the cost: with ``platform_courier`` the zone fee
   is charged to the vendor's payable and booked to ``delivery_revenue`` (it
   pays the rider); with ``self_delivery`` the vendor delivers itself (own
   rider, Yango, ...) and nothing is charged.
2. **Automatic free delivery** (background rule, replaces "free above K200 per
   vendor"). Only when the whole checkout is retail (no wholesale line), its
   item subtotal is at or above the threshold (default K15,000), every line
   has a known weight and the basket weighs less than the limit (default
   500 kg), AND the fees it would waive fit inside the funded share of the
   basket's commission (default 50%). The platform then books the waived fees
   from ``commission_revenue`` to ``delivery_revenue``. If the commission
   cannot fund it, the customer pays as normal (never silently subsidised).
3. Otherwise the **customer pays the zone fee**, booked to ``delivery_revenue``
   (already done by the escrow release / COD collection paths).

Everything here is integer ngwee and pure, so the fulfilment step and
``POST /orders`` compute byte-identical results from the same inputs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

DeliveryFunding = Literal["customer", "vendor", "vendor_self", "platform"]
FreeDeliveryMethod = Literal["platform_courier", "self_delivery"]

DEFAULT_AUTO_FREE_THRESHOLD_NGWEE = 1_500_000  # K15,000
DEFAULT_AUTO_FREE_MAX_WEIGHT_GRAMS = 500_000  # 500 kg
DEFAULT_AUTO_FREE_COMMISSION_SHARE_BPS = 5_000  # 50% of the basket commission
BPS_DENOMINATOR = 10_000


@dataclass(frozen=True, slots=True)
class AutoFreeDeliveryPolicy:
    threshold_ngwee: int = DEFAULT_AUTO_FREE_THRESHOLD_NGWEE
    max_weight_grams: int = DEFAULT_AUTO_FREE_MAX_WEIGHT_GRAMS
    commission_share_bps: int = DEFAULT_AUTO_FREE_COMMISSION_SHARE_BPS

    def __post_init__(self) -> None:
        for name in ("threshold_ngwee", "max_weight_grams", "commission_share_bps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.commission_share_bps > BPS_DENOMINATOR:
            raise ValueError("commission_share_bps must not exceed 10000")


@dataclass(frozen=True, slots=True)
class PricingLine:
    """One cart line, with the facts pricing needs (integer ngwee / grams)."""

    vendor_id: str
    listing_id: str
    qty: int
    line_total_ngwee: int
    commission_bps: int
    wholesale: bool = False
    free_delivery: bool = False
    weight_grams: int | None = None


@dataclass(frozen=True, slots=True)
class VendorDeliveryTerms:
    free_delivery_all: bool = False
    free_delivery_method: FreeDeliveryMethod = "platform_courier"


@dataclass(frozen=True, slots=True)
class GroupDeliveryPrice:
    vendor_id: str
    #: What the customer pays for this group's delivery (ngwee).
    customer_fee_ngwee: int
    funding: DeliveryFunding
    #: Fee booked to delivery_revenue from the vendor payable or commission.
    funded_ngwee: int


def _int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{field} must be non-negative integer")
    return value


def commission_ngwee(line_total_ngwee: int, commission_bps: int) -> int:
    """Floor of line_total × bps / 10000 — never more than the snapshot charges."""
    return (
        _int(line_total_ngwee, "line_total_ngwee") * _int(commission_bps, "commission_bps")
    ) // (BPS_DENOMINATOR)


def basket_auto_free_eligible(lines: Sequence[PricingLine], policy: AutoFreeDeliveryPolicy) -> bool:
    """Retail, at/over the threshold, every weight known and under the limit."""
    if not lines or policy.threshold_ngwee <= 0:
        return False
    if any(line.wholesale for line in lines):
        return False
    subtotal = sum(_int(line.line_total_ngwee, "line_total_ngwee") for line in lines)
    if subtotal < policy.threshold_ngwee:
        return False
    weight = 0
    for line in lines:
        if line.weight_grams is None:
            return False  # unknown weight never qualifies (fail closed)
        weight += _int(line.weight_grams, "weight_grams") * _int(line.qty, "qty")
    return weight < policy.max_weight_grams


def vendor_group_is_free(lines: Iterable[PricingLine], terms: VendorDeliveryTerms | None) -> bool:
    group = list(lines)
    if terms is not None and terms.free_delivery_all:
        return True
    return bool(group) and all(line.free_delivery for line in group)


def price_delivery_groups(
    *,
    lines: Sequence[PricingLine],
    delivery_zones: Mapping[str, str | None],
    zone_fees: Mapping[str, int],
    vendor_terms: Mapping[str, VendorDeliveryTerms],
    policy: AutoFreeDeliveryPolicy,
) -> dict[str, GroupDeliveryPrice]:
    """Price every vendor group.

    ``delivery_zones`` maps each vendor in the checkout to its zone when the
    group is delivered, or ``None`` for pickup / no deliverable zone.
    """
    by_vendor: dict[str, list[PricingLine]] = {}
    for line in lines:
        by_vendor.setdefault(line.vendor_id, []).append(line)

    prices: dict[str, GroupDeliveryPrice] = {}
    customer_paid: list[tuple[str, int]] = []
    for vendor_id in sorted(delivery_zones):
        zone = delivery_zones[vendor_id]
        fee = _int(zone_fees.get(zone, 0), "zone fee") if zone is not None else 0
        if zone is None or fee == 0:
            prices[vendor_id] = GroupDeliveryPrice(vendor_id, 0, "customer", 0)
            continue
        terms = vendor_terms.get(vendor_id)
        if vendor_group_is_free(by_vendor.get(vendor_id, []), terms):
            self_delivery = terms is not None and terms.free_delivery_method == "self_delivery"
            prices[vendor_id] = (
                GroupDeliveryPrice(vendor_id, 0, "vendor_self", 0)
                if self_delivery
                else GroupDeliveryPrice(vendor_id, 0, "vendor", fee)
            )
            continue
        prices[vendor_id] = GroupDeliveryPrice(vendor_id, fee, "customer", 0)
        customer_paid.append((vendor_id, fee))

    if customer_paid and basket_auto_free_eligible(lines, policy):
        budget = (
            sum(commission_ngwee(line.line_total_ngwee, line.commission_bps) for line in lines)
            * policy.commission_share_bps
            // BPS_DENOMINATOR
        )
        waived = sum(fee for _, fee in customer_paid)
        if waived <= budget:
            for vendor_id, fee in customer_paid:
                prices[vendor_id] = GroupDeliveryPrice(vendor_id, 0, "platform", fee)
    return prices


# ---------------------------------------------------------------------------
# Loaders (service-role client; tolerant of missing optional rows)
# ---------------------------------------------------------------------------


def _config_int(rows: Sequence[Mapping[str, Any]], key: str, default: int) -> int:
    for row in rows:
        if row.get("key") != key:
            continue
        raw = row.get("value")
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return default


def load_auto_free_policy(client: Any) -> AutoFreeDeliveryPolicy:
    keys = [
        "auto_free_delivery_threshold_ngwee",
        "auto_free_delivery_max_weight_grams",
        "auto_free_delivery_commission_share_bps",
    ]
    response = client.table("platform_config").select("key, value").in_("key", keys).execute()
    rows = [r for r in (response.data or []) if isinstance(r, dict)]
    share = min(_config_int(rows, keys[2], DEFAULT_AUTO_FREE_COMMISSION_SHARE_BPS), BPS_DENOMINATOR)
    return AutoFreeDeliveryPolicy(
        threshold_ngwee=_config_int(rows, keys[0], DEFAULT_AUTO_FREE_THRESHOLD_NGWEE),
        max_weight_grams=_config_int(rows, keys[1], DEFAULT_AUTO_FREE_MAX_WEIGHT_GRAMS),
        commission_share_bps=share,
    )


@dataclass(frozen=True, slots=True)
class ListingDeliveryFacts:
    free_delivery: bool
    weight_grams: int | None
    commission_bps: int


def load_listing_delivery_facts(
    client: Any, listing_ids: Sequence[str]
) -> dict[str, ListingDeliveryFacts]:
    """Free-delivery flag, unit weight and commission rate per listing."""
    from app.services.orders.create import (
        DEFAULT_COMMISSION_KEY,
        _load_commission_rates,
        _load_listing_commission_keys,
    )

    ids = sorted(set(listing_ids))
    if not ids:
        return {}
    response = (
        client.table("vendor_listings")
        .select("id, free_delivery, weight_grams")
        .in_("id", ids)
        .execute()
    )
    rows = {
        str(r["id"]): r
        for r in (response.data or [])
        if isinstance(r, dict) and isinstance(r.get("id"), str)
    }
    rates = _load_commission_rates(client)
    keys = _load_listing_commission_keys(client, ids)
    facts: dict[str, ListingDeliveryFacts] = {}
    for listing_id in ids:
        row = rows.get(listing_id, {})
        weight = row.get("weight_grams")
        key = keys.get(listing_id, DEFAULT_COMMISSION_KEY)
        facts[listing_id] = ListingDeliveryFacts(
            free_delivery=row.get("free_delivery") is True,
            weight_grams=weight
            if isinstance(weight, int) and not isinstance(weight, bool) and weight > 0
            else None,
            commission_bps=rates.get(key, rates.get(DEFAULT_COMMISSION_KEY, 0)),
        )
    return facts


def load_vendor_delivery_terms(
    client: Any, vendor_ids: Sequence[str]
) -> dict[str, VendorDeliveryTerms]:
    ids = sorted(set(vendor_ids))
    if not ids:
        return {}
    response = (
        client.table("vendors")
        .select("id, free_delivery_all, free_delivery_method")
        .in_("id", ids)
        .execute()
    )
    terms: dict[str, VendorDeliveryTerms] = {}
    for row in response.data or []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        method = row.get("free_delivery_method")
        terms[str(row["id"])] = VendorDeliveryTerms(
            free_delivery_all=row.get("free_delivery_all") is True,
            free_delivery_method="self_delivery"
            if method == "self_delivery"
            else "platform_courier",
        )
    return terms


@dataclass(frozen=True, slots=True)
class RawLine:
    vendor_id: str
    listing_id: str
    qty: int
    unit_price_ngwee: int
    wholesale: bool


def build_pricing_lines(
    raw_lines: Sequence[RawLine], facts: Mapping[str, ListingDeliveryFacts]
) -> list[PricingLine]:
    from app.services.cart.totals import line_total_ngwee

    lines: list[PricingLine] = []
    for raw in raw_lines:
        fact = facts.get(raw.listing_id)
        lines.append(
            PricingLine(
                vendor_id=raw.vendor_id,
                listing_id=raw.listing_id,
                qty=raw.qty,
                line_total_ngwee=line_total_ngwee(raw.qty, raw.unit_price_ngwee),
                commission_bps=fact.commission_bps if fact else 0,
                wholesale=raw.wholesale,
                free_delivery=fact.free_delivery if fact else False,
                weight_grams=fact.weight_grams if fact else None,
            )
        )
    return lines


def price_checkout_delivery(
    client: Any,
    *,
    raw_lines: Sequence[RawLine],
    delivery_zones: Mapping[str, str | None],
    zone_fees: Mapping[str, int],
) -> dict[str, GroupDeliveryPrice]:
    """Load the facts and price every vendor group (fulfilment step + POST /orders)."""
    if not any(zone is not None for zone in delivery_zones.values()):
        return {v: GroupDeliveryPrice(v, 0, "customer", 0) for v in delivery_zones}
    facts = load_listing_delivery_facts(client, [line.listing_id for line in raw_lines])
    terms = load_vendor_delivery_terms(client, list(delivery_zones))
    policy = load_auto_free_policy(client)
    return price_delivery_groups(
        lines=build_pricing_lines(raw_lines, facts),
        delivery_zones=delivery_zones,
        zone_fees=zone_fees,
        vendor_terms=terms,
        policy=policy,
    )
