"""Listing variants: vendor-defined option axes (Colour, Size) and the purchasable
combinations under them, each with its own SKU, stock, optional price override
and photo.

Storage (migration 20261107120000):
  * ``listing_option_groups`` / ``listing_option_values`` with ``kind='variant'``
  * ``vendor_listing_variants`` rows with ``product_variant_id IS NULL`` and a
    sorted ``option_value_ids`` array
  * ``cart_items.listing_variant_id`` and ``order_item_products.listing_variant_id``
    (+ ``variant_snapshot``)

Pricing contract: a variant's ``price_ngwee`` is an override; NULL inherits the
listing price. All money is integer ngwee.

Stock contract: the listing-level ``stock_qty`` remains the reservation pool
claimed at checkout (stock_reservations is keyed per listing). A variant's own
``stock_qty`` (NULL = not tracked separately) is checked on every cart write and
read, and is locked + decremented inside the order transaction
(``public.consume_listing_variant_stock``), so a sold-out variant can never be
ordered even while the listing pool still has units.

A cart holds at most one line per listing (``cart_items`` is unique on
``(cart_id, listing_id)``), so each line carries exactly one variant.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.errors import AppError

VARIANT_ACTIVE = "active"
VARIANT_ARCHIVED = "archived"

MAX_OPTION_GROUPS = 3
MAX_VALUES_PER_GROUP = 30
MAX_VARIANTS = 100
SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,119}$")
SWATCH_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

_VARIANT_SELECT = (
    "id, listing_id, sku_override, option_value_ids, price_ngwee, compare_at_ngwee, "
    "stock_qty, image_public_id, status, position"
)


@dataclass(frozen=True, slots=True)
class OptionValue:
    id: str
    label: str
    swatch_hex: str | None = None
    position: int = 1


@dataclass(frozen=True, slots=True)
class OptionGroup:
    id: str
    name: str
    display: str = "pill"
    position: int = 1
    values: tuple[OptionValue, ...] = ()


@dataclass(frozen=True, slots=True)
class ListingVariant:
    id: str
    listing_id: str
    option_value_ids: tuple[str, ...]
    sku: str | None = None
    price_ngwee: int | None = None
    compare_at_ngwee: int | None = None
    stock_qty: int | None = None
    image_public_id: str | None = None
    status: str = VARIANT_ACTIVE
    position: int = 1

    @property
    def active(self) -> bool:
        return self.status == VARIANT_ACTIVE


@dataclass(frozen=True, slots=True)
class ListingVariantSet:
    listing_id: str
    groups: tuple[OptionGroup, ...] = ()
    variants: tuple[ListingVariant, ...] = ()
    _by_id: dict[str, ListingVariant] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        self._by_id.update({variant.id: variant for variant in self.variants})

    @property
    def active_variants(self) -> tuple[ListingVariant, ...]:
        return tuple(variant for variant in self.variants if variant.active)

    @property
    def requires_variant(self) -> bool:
        """A listing with option groups and at least one active variant must be
        bought as a specific variant."""
        return bool(self.groups) and bool(self.active_variants)

    def get(self, variant_id: str | None) -> ListingVariant | None:
        if not variant_id:
            return None
        return self._by_id.get(variant_id)

    def options_for(self, variant: ListingVariant) -> list[dict[str, str]]:
        """Ordered ``[{"group": "Colour", "value": "Red"}, ...]`` for display."""
        wanted = set(variant.option_value_ids)
        pairs: list[dict[str, str]] = []
        for group in self.groups:
            for value in group.values:
                if value.id in wanted:
                    pairs.append({"group": group.name, "value": value.label})
                    break
        return pairs


EMPTY_SET = ListingVariantSet(listing_id="")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    return int(value)


def parse_variant_row(row: Mapping[str, Any]) -> ListingVariant:
    raw_ids = row.get("option_value_ids") or []
    return ListingVariant(
        id=str(row["id"]),
        listing_id=str(row.get("listing_id") or ""),
        option_value_ids=tuple(sorted(str(value) for value in raw_ids)),
        sku=str(row["sku_override"]) if row.get("sku_override") else None,
        price_ngwee=_opt_int(row.get("price_ngwee")),
        compare_at_ngwee=_opt_int(row.get("compare_at_ngwee")),
        stock_qty=_opt_int(row.get("stock_qty")),
        image_public_id=str(row["image_public_id"]) if row.get("image_public_id") else None,
        status=str(row.get("status") or VARIANT_ACTIVE),
        position=int(row.get("position") or 1),
    )


def build_variant_sets(
    listing_ids: Iterable[str],
    *,
    group_rows: Sequence[Mapping[str, Any]],
    value_rows: Sequence[Mapping[str, Any]],
    variant_rows: Sequence[Mapping[str, Any]],
) -> dict[str, ListingVariantSet]:
    """Assemble variant sets from raw rows (pure; unit-tested directly)."""
    values_by_group: dict[str, list[OptionValue]] = {}
    for row in value_rows:
        values_by_group.setdefault(str(row["group_id"]), []).append(
            OptionValue(
                id=str(row["id"]),
                label=str(row.get("label") or ""),
                swatch_hex=str(row["swatch_hex"]) if row.get("swatch_hex") else None,
                position=int(row.get("position") or 1),
            )
        )
    groups_by_listing: dict[str, list[OptionGroup]] = {}
    for row in group_rows:
        group_id = str(row["id"])
        values = sorted(values_by_group.get(group_id, []), key=lambda value: value.position)
        groups_by_listing.setdefault(str(row["listing_id"]), []).append(
            OptionGroup(
                id=group_id,
                name=str(row.get("name") or ""),
                display=str(row.get("display") or "pill"),
                position=int(row.get("position") or 1),
                values=tuple(values),
            )
        )
    variants_by_listing: dict[str, list[ListingVariant]] = {}
    for row in variant_rows:
        variant = parse_variant_row(row)
        variants_by_listing.setdefault(variant.listing_id, []).append(variant)

    sets: dict[str, ListingVariantSet] = {}
    for listing_id in listing_ids:
        groups = sorted(groups_by_listing.get(listing_id, []), key=lambda group: group.position)
        variants = sorted(
            variants_by_listing.get(listing_id, []), key=lambda variant: variant.position
        )
        sets[listing_id] = ListingVariantSet(
            listing_id=listing_id, groups=tuple(groups), variants=tuple(variants)
        )
    return sets


def load_variant_sets(client: Any, listing_ids: Iterable[str]) -> dict[str, ListingVariantSet]:
    """Load variant axes + variants (archived included) for listings.

    ``client`` is a supabase ``Client`` (service role on the API side).
    """
    ids = sorted({str(listing_id) for listing_id in listing_ids if listing_id})
    if not ids:
        return {}
    group_rows = _rows(
        client.table("listing_option_groups")
        .select("id, listing_id, name, display, position")
        .in_("listing_id", ids)
        .eq("kind", "variant")
        .execute()
    )
    group_ids = [str(row["id"]) for row in group_rows]
    value_rows = (
        _rows(
            client.table("listing_option_values")
            .select("id, group_id, label, swatch_hex, position")
            .in_("group_id", group_ids)
            .execute()
        )
        if group_ids
        else []
    )
    # Canonical-product links (product_variant_id set) are a separate model;
    # only listing-defined combinations are purchasable variants here.
    variant_rows = [
        row
        for row in _rows(
            client.table("vendor_listing_variants")
            .select(_VARIANT_SELECT + ", product_variant_id")
            .in_("listing_id", ids)
            .execute()
        )
        if row.get("product_variant_id") is None
    ]
    return build_variant_sets(
        ids, group_rows=group_rows, value_rows=value_rows, variant_rows=variant_rows
    )


# ---------------------------------------------------------------------------
# Price / stock semantics
# ---------------------------------------------------------------------------


def effective_price_ngwee(listing: Mapping[str, Any], variant: ListingVariant | None) -> int:
    if variant is not None and variant.price_ngwee is not None:
        return int(variant.price_ngwee)
    return int(listing["price_ngwee"])


def _stock_not_governed(listing: Mapping[str, Any]) -> bool:
    return (
        str(listing.get("product_class") or "A") == "E"
        or str(listing.get("fulfilment_mode") or "stocked") == "made_to_order"
        or listing.get("stock_mode") == "always_available"
    )


def variant_available_qty(listing: Mapping[str, Any], variant: ListingVariant) -> int | None:
    """Units purchasable for this variant; ``None`` = not limited at variant level."""
    if not variant.active:
        return 0
    if _stock_not_governed(listing) or variant.stock_qty is None:
        return None
    return max(int(variant.stock_qty), 0)


def variant_in_stock(listing: Mapping[str, Any], variant: ListingVariant) -> bool:
    available = variant_available_qty(listing, variant)
    return available is None or available > 0


def resolve_variant_for_purchase(
    variant_set: ListingVariantSet,
    *,
    listing: Mapping[str, Any],
    variant_id: str | None,
    qty: int,
) -> ListingVariant | None:
    """Validate a buyer's variant choice for a cart write.

    Fails closed: a listing with variants cannot be bought without one; a
    variant id must belong to THIS listing; archived variants and quantities
    above the variant's own stock are refused.
    """
    listing_id = str(listing.get("id") or variant_set.listing_id)
    if not variant_id:
        if variant_set.requires_variant:
            raise AppError(
                code="cart.variant_required",
                message="Choose the options for this item before adding it to your cart",
                http_status=422,
                details={"listing_id": listing_id, "message_key": "cart.variant_required"},
            )
        return None

    variant = variant_set.get(variant_id)
    if variant is None or variant.listing_id != listing_id:
        # Same answer for "unknown id" and "id of another listing's variant".
        raise AppError(
            code="cart.variant_invalid",
            message="That option does not belong to this item",
            http_status=422,
            details={
                "listing_id": listing_id,
                "listing_variant_id": variant_id,
                "message_key": "cart.variant_invalid",
            },
        )
    if not variant.active:
        raise AppError(
            code="cart.variant_unavailable",
            message="That option is no longer available",
            http_status=409,
            details={
                "listing_id": listing_id,
                "listing_variant_id": variant_id,
                "message_key": "cart.variant_unavailable",
                "retry": False,
            },
        )
    available = variant_available_qty(listing, variant)
    if available is not None and qty > available:
        raise AppError(
            code="cart.variant_out_of_stock",
            message="Not enough stock for that option",
            http_status=409,
            details={
                "listing_id": listing_id,
                "listing_variant_id": variant_id,
                "available_qty": available,
                "requested_qty": qty,
                "message_key": "cart.variant_out_of_stock",
                "retry": True,
            },
        )
    return variant


def overlay_listing_for_variant(
    listing: Mapping[str, Any],
    variant_set: ListingVariantSet | None,
    variant_id: str | None,
) -> dict[str, Any]:
    """Return a listing dict as seen by ONE cart line carrying ``variant_id``.

    Downstream price derivation (read path, checkout re-derivation, merge) reads
    ``price_ngwee`` from the listing, so the effective variant price is placed
    there. ``_variant_*`` keys carry presentation data and availability.
    """
    view = dict(listing)
    if not variant_id:
        if variant_set is not None and variant_set.requires_variant:
            view["_variant_required"] = True
        return view
    variant = variant_set.get(variant_id) if variant_set is not None else None
    view["_variant_id"] = variant_id
    if variant is None or not variant.active:
        view["_variant_unavailable"] = True
        return view
    view["price_ngwee"] = effective_price_ngwee(listing, variant)
    if variant_set is not None:
        view["_variant_options"] = variant_set.options_for(variant)
    view["_variant_sku"] = variant.sku
    view["_variant_image_public_id"] = variant.image_public_id
    available = variant_available_qty(listing, variant)
    if available is not None:
        view["_variant_available_qty"] = available
    return view


def overlay_listings_for_items(
    items: Sequence[Mapping[str, Any]],
    listings_by_id: Mapping[str, dict[str, Any]],
    variant_sets: Mapping[str, ListingVariantSet],
) -> dict[str, dict[str, Any]]:
    overlaid = dict(listings_by_id)
    for item in items:
        listing_id = str(item["listing_id"])
        listing = listings_by_id.get(listing_id)
        if listing is None:
            continue
        raw_variant = item.get("listing_variant_id")
        variant_id = str(raw_variant) if isinstance(raw_variant, str) and raw_variant else None
        overlaid[listing_id] = overlay_listing_for_variant(
            listing, variant_sets.get(listing_id), variant_id
        )
    return overlaid


def snapshot_options(snapshot: Any) -> list[dict[str, str]]:
    """Read ``options`` back out of a stored ``variant_snapshot`` defensively."""
    if not isinstance(snapshot, Mapping):
        return []
    options = snapshot.get("options")
    if not isinstance(options, list):
        return []
    pairs: list[dict[str, str]] = []
    for option in options:
        if isinstance(option, Mapping) and option.get("group") and option.get("value"):
            pairs.append({"group": str(option["group"]), "value": str(option["value"])})
    return pairs


# ---------------------------------------------------------------------------
# Vendor payload validation (shape is enforced by Pydantic; this is semantics)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroupSpec:
    name: str
    display: str
    values: tuple[tuple[str, str | None], ...]  # (label, swatch_hex)


@dataclass(frozen=True, slots=True)
class VariantSpec:
    options: tuple[str, ...]
    sku: str | None
    stock_qty: int | None
    price_ngwee: int | None
    compare_at_ngwee: int | None
    image_public_id: str | None
    status: str


def _invalid(field_path: str, reason: str, **extra: Any) -> AppError:
    return AppError(
        code="variants.invalid",
        message="Variant options are invalid",
        http_status=422,
        details={
            "field": field_path,
            "reason": reason,
            "message_key": f"vendor.listings.variants.errors.{reason}",
            **extra,
        },
    )


def validate_variant_payload(
    groups: Sequence[GroupSpec],
    variants: Sequence[VariantSpec],
    *,
    listing: Mapping[str, Any],
    listing_image_ids: Iterable[str],
) -> None:
    """Semantic validation for ``PUT /vendor/listings/{id}/variants``.

    Raises ``AppError(variants.invalid)`` whose ``details.reason`` maps 1:1 to a
    vendor i18n key, so the editor can point at the offending field.
    """
    product_class = str(listing.get("product_class") or "A")
    if groups or variants:
        if product_class == "E":
            raise _invalid("groups", "classEUnsupported")
        if listing.get("wholesale") or listing.get("price_tiers"):
            raise _invalid("groups", "wholesaleUnsupported")
        if str(listing.get("sale_unit") or "each") != "each":
            raise _invalid("groups", "measuredUnsupported")

    if len(groups) > MAX_OPTION_GROUPS:
        raise _invalid("groups", "tooManyGroups", max=MAX_OPTION_GROUPS)

    seen_names: set[str] = set()
    labels_by_group: list[set[str]] = []
    for gi, group in enumerate(groups):
        name = group.name.strip()
        if not name or len(name) > 80:
            raise _invalid(f"groups.{gi}.name", "groupNameRequired")
        if name.casefold() in seen_names:
            raise _invalid(f"groups.{gi}.name", "duplicateGroup")
        seen_names.add(name.casefold())
        if group.display not in {"pill", "swatch"}:
            raise _invalid(f"groups.{gi}.display", "invalidDisplay")
        if not group.values:
            raise _invalid(f"groups.{gi}.values", "valuesRequired")
        if len(group.values) > MAX_VALUES_PER_GROUP:
            raise _invalid(f"groups.{gi}.values", "tooManyValues", max=MAX_VALUES_PER_GROUP)
        seen_labels: set[str] = set()
        for vi, (label, swatch) in enumerate(group.values):
            clean = label.strip()
            if not clean or len(clean) > 120:
                raise _invalid(f"groups.{gi}.values.{vi}.label", "valueLabelRequired")
            if clean.casefold() in seen_labels:
                raise _invalid(f"groups.{gi}.values.{vi}.label", "duplicateValue")
            seen_labels.add(clean.casefold())
            if swatch is not None and not SWATCH_RE.fullmatch(swatch):
                raise _invalid(f"groups.{gi}.values.{vi}.swatch_hex", "invalidSwatch")
        labels_by_group.append(seen_labels)

    if not groups:
        if variants:
            raise _invalid("variants", "groupsRequired")
        return
    if not variants:
        raise _invalid("variants", "variantsRequired")
    if len(variants) > MAX_VARIANTS:
        raise _invalid("variants", "tooManyVariants", max=MAX_VARIANTS)

    image_ids = set(listing_image_ids)
    listing_price = int(listing.get("price_ngwee") or 0)
    seen_combos: set[tuple[str, ...]] = set()
    seen_skus: set[str] = set()
    for index, variant in enumerate(variants):
        if len(variant.options) != len(groups):
            raise _invalid(f"variants.{index}.options", "optionPerGroup")
        combo = tuple(option.strip().casefold() for option in variant.options)
        for gi, label in enumerate(combo):
            if label not in labels_by_group[gi]:
                raise _invalid(f"variants.{index}.options.{gi}", "unknownValue")
        if combo in seen_combos:
            raise _invalid(f"variants.{index}.options", "duplicateCombination")
        seen_combos.add(combo)
        if variant.sku is not None:
            sku = variant.sku.strip()
            if not SKU_RE.fullmatch(sku):
                raise _invalid(f"variants.{index}.sku", "invalidSku")
            if sku.casefold() in seen_skus:
                raise _invalid(f"variants.{index}.sku", "duplicateSku")
            seen_skus.add(sku.casefold())
        if variant.stock_qty is not None and variant.stock_qty < 0:
            raise _invalid(f"variants.{index}.stock_qty", "invalidStock")
        if variant.price_ngwee is not None and variant.price_ngwee <= 0:
            raise _invalid(f"variants.{index}.price_ngwee", "invalidPrice")
        effective = variant.price_ngwee if variant.price_ngwee is not None else listing_price
        if variant.compare_at_ngwee is not None and variant.compare_at_ngwee <= effective:
            raise _invalid(f"variants.{index}.compare_at_ngwee", "invalidCompareAt")
        if variant.image_public_id is not None and variant.image_public_id not in image_ids:
            raise _invalid(f"variants.{index}.image_public_id", "imageNotOnListing")
        if variant.status not in {VARIANT_ACTIVE, VARIANT_ARCHIVED}:
            raise _invalid(f"variants.{index}.status", "invalidStatus")

    if not any(variant.status == VARIANT_ACTIVE for variant in variants):
        raise _invalid("variants", "activeVariantRequired")
