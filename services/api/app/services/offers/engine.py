"""Pure, deterministic offer pricing engine (W8). Integer ngwee only.

Given the cart lines and the active offers of their vendors it returns, per
line, the list total, the discounted total and the offer that priced it, plus
the free gift lines. The same function prices the cart view, the checkout
session and order placement, so the amounts agree everywhere; placement then
snapshots the result on the order lines and never recomputes it.

Rules
-----
* One offer per cart line (no stacking). Offers are evaluated in a fixed
  order: bundle, buy_n_pay_m, bxgy, free_gift; within a type by offer id.
* Product lines and event-ticket lines are priced here (the unified cart holds
  both; a ticket line carries ``item_kind="event"`` and the event id as its
  ref). An offer that needs a service item is not cart-applicable
  (``cart_applicable`` False) — services are still booked on their own flow —
  and its storefront badge is suppressed too. bundle and buy_n_pay_m may mix
  products and event tickets; bxgy / free_gift stay product-only (the free gift
  is a product shipped in a goods order, so its trigger must be one too).
* bundle: sets = min(line qty // item qty) over anchor + add-ons. Percent mode
  discounts the add-ons only (floor(addon_total * pct / 100)), allocated across
  the add-on lines; fixed mode allocates (set list total - bundle price) across
  every line of the set. Allocation is largest-remainder (allocation.py).
* buy_n_pay_m: eligible units sorted by unit price desc (then line key) and
  chunked by N; the (N - M) cheapest units of each full chunk are free. The
  discount is allocated across the participating lines by their chunked value.
* bxgy / free_gift: per ``buy_qty`` trigger units the customer gets
  ``get_qty`` reward units at price 0, capped by max applications and by the
  gift pool still available. The trigger lines keep their price. An offer whose
  pool is empty is skipped (the storefront hides it).
* A discount never prices a paid unit below 1 ngwee: if the allocation would,
  the offer is skipped for that cart (fail safe, customer pays list price).
* ``max_discount_pct`` (admin abuse cap) is re-checked at pricing time against
  live list prices; an offer exceeding it is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.offers.allocation import allocate_pro_rata, percent_of

OfferType = Literal["bxgy", "bundle", "buy_n_pay_m", "free_gift"]
ItemRole = Literal["trigger", "reward", "anchor", "addon", "eligible"]
ItemKind = Literal["product", "service", "event"]

TYPE_ORDER: dict[str, int] = {"bundle": 0, "buy_n_pay_m": 1, "bxgy": 2, "free_gift": 3}
DEFAULT_MAX_DISCOUNT_PCT = 90


@dataclass(frozen=True, slots=True)
class PricingLine:
    key: str
    #: Listing id for a product line; event id for an event-ticket line.
    listing_id: str
    vendor_id: str
    qty: int
    unit_price_ngwee: int
    item_kind: ItemKind = "product"


@dataclass(frozen=True, slots=True)
class OfferItemDef:
    role: ItemRole
    item_kind: ItemKind
    ref_id: str
    qty: int = 1


@dataclass(frozen=True, slots=True)
class OfferDef:
    id: str
    vendor_id: str
    offer_type: OfferType
    title: str
    items: tuple[OfferItemDef, ...]
    buy_qty: int | None = None
    get_qty: int | None = None
    bundle_pricing: str | None = None
    addon_percent_off: int | None = None
    bundle_price_ngwee: int | None = None
    buy_n: int | None = None
    pay_m: int | None = None
    #: Gift units still available (total - reserved); None = no pool.
    gift_available: int | None = None
    max_applications_per_order: int = 1
    #: Live list price of the reward listing (gift reference value).
    reward_unit_price_ngwee: int | None = None
    reward_title: str | None = None

    def items_with_role(self, *roles: str) -> tuple[OfferItemDef, ...]:
        return tuple(item for item in self.items if item.role in roles)

    @property
    def cart_applicable(self) -> bool:
        """True when the unified cart can honour it: products and event tickets
        only (no service item) and any reward is a product."""
        if self.offer_type in ("bxgy", "free_gift"):
            # A free product gift ships in a goods order with its own fulfilment
            # choice; a ticket-triggered gift is not applied in this slice.
            return all(item.item_kind == "product" for item in self.items)
        return all(item.item_kind in ("product", "event") for item in self.items)


@dataclass(frozen=True, slots=True)
class LineOutcome:
    key: str
    list_total_ngwee: int
    final_total_ngwee: int
    offer_id: str | None = None

    @property
    def discount_ngwee(self) -> int:
        return self.list_total_ngwee - self.final_total_ngwee


@dataclass(frozen=True, slots=True)
class GiftOutcome:
    offer_id: str
    vendor_id: str
    listing_id: str
    qty: int
    reference_unit_price_ngwee: int
    parent_key: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class OfferApplication:
    offer_id: str
    offer_type: str
    vendor_id: str
    title: str
    applications: int
    discount_ngwee: int
    gift_qty: int
    line_keys: tuple[str, ...]
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PricedCart:
    lines: dict[str, LineOutcome]
    gifts: tuple[GiftOutcome, ...]
    applications: tuple[OfferApplication, ...]

    @property
    def subtotal_ngwee(self) -> int:
        return sum(outcome.final_total_ngwee for outcome in self.lines.values())

    @property
    def savings_ngwee(self) -> int:
        return sum(outcome.discount_ngwee for outcome in self.lines.values())

    @property
    def gift_value_ngwee(self) -> int:
        return sum(g.qty * g.reference_unit_price_ngwee for g in self.gifts)

    def application_for(self, offer_id: str) -> OfferApplication | None:
        for application in self.applications:
            if application.offer_id == offer_id:
                return application
        return None


def offer_snapshot(offer: OfferDef) -> dict[str, Any]:
    """The immutable terms stored on every order line the offer priced."""
    return {
        "offer_id": offer.id,
        "offer_type": offer.offer_type,
        "title": offer.title,
        "buy_qty": offer.buy_qty,
        "get_qty": offer.get_qty,
        "bundle_pricing": offer.bundle_pricing,
        "addon_percent_off": offer.addon_percent_off,
        "bundle_price_ngwee": offer.bundle_price_ngwee,
        "buy_n": offer.buy_n,
        "pay_m": offer.pay_m,
        "items": [
            {"role": i.role, "item_kind": i.item_kind, "ref_id": i.ref_id, "qty": i.qty}
            for i in offer.items
        ],
    }


class _Claims:
    def __init__(self, lines: list[PricingLine]) -> None:
        self.by_ref: dict[tuple[str, str, str], list[PricingLine]] = {}
        for line in lines:
            self.by_ref.setdefault((line.vendor_id, line.item_kind, line.listing_id), []).append(
                line
            )
        self.claimed: set[str] = set()

    def free_lines(self, vendor_id: str, item: OfferItemDef) -> list[PricingLine]:
        """Unclaimed cart lines matching an offer item (same kind and ref)."""
        return [
            line
            for line in self.by_ref.get((vendor_id, item.item_kind, item.ref_id), [])
            if line.key not in self.claimed
        ]


def _discount_valid(list_totals: list[int], discounts: list[int], qtys: list[int]) -> bool:
    return all(
        total - discount >= qty
        for total, discount, qty in zip(list_totals, discounts, qtys, strict=True)
    )


def _within_cap(discount: int, list_value: int, max_discount_pct: int) -> bool:
    return list_value > 0 and discount * 100 <= list_value * max_discount_pct


def _price_bundle(
    offer: OfferDef,
    claims: _Claims,
    outcomes: dict[str, LineOutcome],
    max_discount_pct: int,
) -> OfferApplication | None:
    anchors = offer.items_with_role("anchor")
    addons = offer.items_with_role("addon")
    if len(anchors) != 1 or not addons:
        return None
    members: list[tuple[OfferItemDef, PricingLine]] = []
    for item in (*anchors, *addons):
        candidates = claims.free_lines(offer.vendor_id, item)
        if not candidates:
            return None
        # Deterministic: the line with the most units, then by key.
        line = sorted(candidates, key=lambda c: (-c.qty, c.key))[0]
        members.append((item, line))
    if len({line.key for _, line in members}) != len(members):
        return None
    sets = min(line.qty // item.qty for item, line in members)
    sets = min(sets, offer.max_applications_per_order)
    if sets <= 0:
        return None
    set_values = [line.unit_price_ngwee * item.qty * sets for item, line in members]
    full_list = sum(set_values)
    if offer.bundle_pricing == "addon_percent_off" and offer.addon_percent_off is not None:
        addon_values = set_values[1:]
        discount = percent_of(sum(addon_values), offer.addon_percent_off)
        shares = [0, *allocate_pro_rata(discount, addon_values)]
    elif offer.bundle_pricing == "fixed_price" and offer.bundle_price_ngwee is not None:
        target = offer.bundle_price_ngwee * sets
        if target >= full_list:
            return None
        discount = full_list - target
        shares = allocate_pro_rata(discount, set_values)
    else:
        return None
    if discount <= 0 or not _within_cap(discount, full_list, max_discount_pct):
        return None
    lines = [line for _, line in members]
    list_totals = [line.qty * line.unit_price_ngwee for line in lines]
    if not _discount_valid(list_totals, shares, [line.qty for line in lines]):
        return None
    for line, list_total, share in zip(lines, list_totals, shares, strict=True):
        claims.claimed.add(line.key)
        outcomes[line.key] = LineOutcome(
            key=line.key,
            list_total_ngwee=list_total,
            final_total_ngwee=list_total - share,
            offer_id=offer.id,
        )
    return OfferApplication(
        offer_id=offer.id,
        offer_type=offer.offer_type,
        vendor_id=offer.vendor_id,
        title=offer.title,
        applications=sets,
        discount_ngwee=discount,
        gift_qty=0,
        line_keys=tuple(line.key for line in lines),
        snapshot=offer_snapshot(offer),
    )


def _price_buy_n_pay_m(
    offer: OfferDef,
    claims: _Claims,
    outcomes: dict[str, LineOutcome],
    max_discount_pct: int,
) -> OfferApplication | None:
    n, m = offer.buy_n, offer.pay_m
    if n is None or m is None or not 1 <= m < n:
        return None
    lines: list[PricingLine] = []
    seen: set[str] = set()
    for item in offer.items_with_role("eligible"):
        for line in claims.free_lines(offer.vendor_id, item):
            if line.key not in seen:
                seen.add(line.key)
                lines.append(line)
    units: list[tuple[int, str]] = []
    for line in lines:
        units.extend((line.unit_price_ngwee, line.key) for _ in range(line.qty))
    units.sort(key=lambda unit: (-unit[0], unit[1]))
    chunks = min(len(units) // n, offer.max_applications_per_order)
    if chunks <= 0:
        return None
    discount = 0
    chunk_value: dict[str, int] = {}
    for index in range(chunks):
        chunk = units[index * n : (index + 1) * n]
        for price, key in chunk:
            chunk_value[key] = chunk_value.get(key, 0) + price
        discount += sum(price for price, _ in chunk[m:])
    participating = [line for line in lines if line.key in chunk_value]
    weights = [chunk_value[line.key] for line in participating]
    if discount <= 0 or not _within_cap(discount, sum(weights), max_discount_pct):
        return None
    shares = allocate_pro_rata(discount, weights)
    list_totals = [line.qty * line.unit_price_ngwee for line in participating]
    if not _discount_valid(list_totals, shares, [line.qty for line in participating]):
        return None
    for line, list_total, share in zip(participating, list_totals, shares, strict=True):
        claims.claimed.add(line.key)
        outcomes[line.key] = LineOutcome(
            key=line.key,
            list_total_ngwee=list_total,
            final_total_ngwee=list_total - share,
            offer_id=offer.id,
        )
    return OfferApplication(
        offer_id=offer.id,
        offer_type=offer.offer_type,
        vendor_id=offer.vendor_id,
        title=offer.title,
        applications=chunks,
        discount_ngwee=discount,
        gift_qty=0,
        line_keys=tuple(line.key for line in participating),
        snapshot=offer_snapshot(offer),
    )


def _price_gift(
    offer: OfferDef,
    claims: _Claims,
    outcomes: dict[str, LineOutcome],
    gifts: list[GiftOutcome],
) -> OfferApplication | None:
    rewards = offer.items_with_role("reward")
    triggers = offer.items_with_role("trigger")
    if len(rewards) != 1 or not triggers:
        return None
    reward = rewards[0]
    if offer.reward_unit_price_ngwee is None or offer.reward_unit_price_ngwee <= 0:
        return None
    if offer.offer_type == "bxgy":
        buy_qty = offer.buy_qty or 0
        get_qty = (offer.get_qty or 0) * reward.qty
    else:
        buy_qty = 1
        get_qty = reward.qty
    if buy_qty <= 0 or get_qty <= 0:
        return None
    lines: list[PricingLine] = []
    seen: set[str] = set()
    for item in triggers:
        for line in claims.free_lines(offer.vendor_id, item):
            if line.key not in seen:
                seen.add(line.key)
                lines.append(line)
    trigger_units = sum(line.qty for line in lines)
    applications = min(trigger_units // buy_qty, offer.max_applications_per_order)
    available = offer.gift_available if offer.gift_available is not None else 0
    applications = min(applications, available // get_qty)
    if applications <= 0:
        return None
    lines.sort(key=lambda line: line.key)
    for line in lines:
        claims.claimed.add(line.key)
        outcomes[line.key] = LineOutcome(
            key=line.key,
            list_total_ngwee=line.qty * line.unit_price_ngwee,
            final_total_ngwee=line.qty * line.unit_price_ngwee,
            offer_id=offer.id,
        )
    gift_qty = applications * get_qty
    gifts.append(
        GiftOutcome(
            offer_id=offer.id,
            vendor_id=offer.vendor_id,
            listing_id=reward.ref_id,
            qty=gift_qty,
            reference_unit_price_ngwee=offer.reward_unit_price_ngwee,
            parent_key=lines[0].key,
            title=offer.reward_title,
        )
    )
    return OfferApplication(
        offer_id=offer.id,
        offer_type=offer.offer_type,
        vendor_id=offer.vendor_id,
        title=offer.title,
        applications=applications,
        discount_ngwee=0,
        gift_qty=gift_qty,
        line_keys=tuple(line.key for line in lines),
        snapshot=offer_snapshot(offer),
    )


def price_cart(
    lines: list[PricingLine],
    offers: list[OfferDef],
    *,
    max_discount_pct: int = DEFAULT_MAX_DISCOUNT_PCT,
) -> PricedCart:
    """Apply ``offers`` to ``lines``. Deterministic; never mutates its inputs."""
    for line in lines:
        if line.qty <= 0 or line.unit_price_ngwee <= 0:
            raise ValueError("pricing lines need positive qty and unit price")
    claims = _Claims(lines)
    outcomes: dict[str, LineOutcome] = {}
    gifts: list[GiftOutcome] = []
    applications: list[OfferApplication] = []
    vendors_in_cart = {line.vendor_id for line in lines}
    ordered = sorted(
        (o for o in offers if o.vendor_id in vendors_in_cart and o.cart_applicable),
        key=lambda o: (TYPE_ORDER.get(o.offer_type, 99), o.id),
    )
    for offer in ordered:
        application: OfferApplication | None
        if offer.offer_type == "bundle":
            application = _price_bundle(offer, claims, outcomes, max_discount_pct)
        elif offer.offer_type == "buy_n_pay_m":
            application = _price_buy_n_pay_m(offer, claims, outcomes, max_discount_pct)
        elif offer.offer_type in ("bxgy", "free_gift"):
            application = _price_gift(offer, claims, outcomes, gifts)
        else:
            application = None
        if application is not None:
            applications.append(application)
    for line in lines:
        if line.key not in outcomes:
            total = line.qty * line.unit_price_ngwee
            outcomes[line.key] = LineOutcome(
                key=line.key, list_total_ngwee=total, final_total_ngwee=total
            )
    return PricedCart(lines=outcomes, gifts=tuple(gifts), applications=tuple(applications))
