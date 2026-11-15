"""W8 offers — request/response models (Pydantic v2 strict, integer ngwee)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.base import NgweeInt, StrictModel

OfferTypeIn = Literal["bxgy", "bundle", "buy_n_pay_m", "free_gift"]
OfferStatusIn = Literal["draft", "active", "paused"]
OfferStatusOut = Literal["draft", "active", "paused", "archived"]
ItemRoleIn = Literal["trigger", "reward", "anchor", "addon", "eligible"]
ItemKindIn = Literal["product", "service", "event"]
BundlePricingIn = Literal["addon_percent_off", "fixed_price"]
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
# JSON bodies carry ISO-8601 strings; strict mode would refuse them.
IsoDateTime = Annotated[datetime, Field(strict=False)]

MAX_ADDONS = 5
MAX_TRIGGERS = 20
MAX_ELIGIBLE = 20

# Which roles each type takes, and which fields belong to it.
TYPE_ROLES: dict[str, frozenset[str]] = {
    "bxgy": frozenset({"trigger", "reward"}),
    "free_gift": frozenset({"trigger", "reward"}),
    "bundle": frozenset({"anchor", "addon"}),
    "buy_n_pay_m": frozenset({"eligible"}),
}
TYPE_FIELDS: dict[str, frozenset[str]] = {
    "bxgy": frozenset({"buy_qty", "get_qty", "gift_stock_total"}),
    "free_gift": frozenset({"gift_stock_total"}),
    "bundle": frozenset({"bundle_pricing", "addon_percent_off", "bundle_price_ngwee"}),
    "buy_n_pay_m": frozenset({"buy_n", "pay_m"}),
}
OPTIONAL_TYPE_FIELDS = (
    "buy_qty",
    "get_qty",
    "gift_stock_total",
    "bundle_pricing",
    "addon_percent_off",
    "bundle_price_ngwee",
    "buy_n",
    "pay_m",
)


class OfferItemIn(StrictModel):
    role: ItemRoleIn
    item_kind: ItemKindIn
    ref_id: str = Field(pattern=UUID_PATTERN)
    qty: int = Field(default=1, ge=1, le=100)


class OfferWriteRequest(StrictModel):
    offer_type: OfferTypeIn
    title: str = Field(min_length=1, max_length=120)
    status: OfferStatusIn = "draft"
    starts_at: IsoDateTime | None = None
    ends_at: IsoDateTime | None = None
    buy_qty: int | None = Field(default=None, ge=1, le=100)
    get_qty: int | None = Field(default=None, ge=1, le=100)
    bundle_pricing: BundlePricingIn | None = None
    addon_percent_off: int | None = Field(default=None, ge=1, le=95)
    bundle_price_ngwee: NgweeInt | None = None
    buy_n: int | None = Field(default=None, ge=2, le=100)
    pay_m: int | None = Field(default=None, ge=1, le=99)
    gift_stock_total: int | None = Field(default=None, ge=0, le=1_000_000)
    max_applications_per_order: int = Field(default=1, ge=1, le=20)
    #: Orders per customer that may use this offer (None = unlimited). Mirrors
    #: offers_per_customer_limit_check; enforced under the offer row lock at
    #: order placement (services/orders/create.py).
    per_customer_limit: int | None = Field(default=None, ge=1, le=1000)
    items: list[OfferItemIn] = Field(min_length=1, max_length=MAX_TRIGGERS + 1)

    @model_validator(mode="after")
    def _shape(self) -> OfferWriteRequest:
        errors: dict[str, str] = {}
        title = self.title.strip()
        if not title:
            errors["title"] = "required"
        allowed = TYPE_FIELDS[self.offer_type]
        for name in OPTIONAL_TYPE_FIELDS:
            if name not in allowed and getattr(self, name) is not None:
                errors[name] = "not_allowed_for_type"
        roles = [item.role for item in self.items]
        if any(role not in TYPE_ROLES[self.offer_type] for role in roles):
            errors["items"] = "role_not_allowed_for_type"
        keys = [(item.role, item.ref_id.lower()) for item in self.items]
        if len(set(keys)) != len(keys):
            errors["items"] = "duplicate_item"
        if self.offer_type in ("bxgy", "free_gift"):
            if roles.count("reward") != 1:
                errors["items"] = "exactly_one_reward"
            elif not 1 <= roles.count("trigger") <= MAX_TRIGGERS:
                errors["items"] = "trigger_required"
            reward = next((i for i in self.items if i.role == "reward"), None)
            if reward is not None and reward.item_kind != "product":
                errors["items"] = "reward_must_be_product"
            if (
                reward is not None
                and any(i.role == "trigger" and i.ref_id == reward.ref_id for i in self.items)
                and self.offer_type == "free_gift"
            ):
                errors["items"] = "gift_must_differ_from_trigger"
            if self.gift_stock_total is None:
                errors["gift_stock_total"] = "required"
            if self.offer_type == "bxgy":
                if self.buy_qty is None:
                    errors["buy_qty"] = "required"
                if self.get_qty is None:
                    errors["get_qty"] = "required"
        elif self.offer_type == "bundle":
            if roles.count("anchor") != 1:
                errors["items"] = "exactly_one_anchor"
            elif not 1 <= roles.count("addon") <= MAX_ADDONS:
                errors["items"] = "addons_required"
            elif any(i.item_kind == "service" for i in self.items):
                # Products and event tickets share the unified cart; services
                # are still booked on their own flow.
                errors["items"] = "bundle_products_only"
            if self.bundle_pricing is None:
                errors["bundle_pricing"] = "required"
            elif self.bundle_pricing == "addon_percent_off":
                if self.addon_percent_off is None:
                    errors["addon_percent_off"] = "required"
                if self.bundle_price_ngwee is not None:
                    errors["bundle_price_ngwee"] = "not_allowed_for_pricing"
            else:
                if self.bundle_price_ngwee is None or self.bundle_price_ngwee <= 0:
                    errors["bundle_price_ngwee"] = "required"
                if self.addon_percent_off is not None:
                    errors["addon_percent_off"] = "not_allowed_for_pricing"
        else:  # buy_n_pay_m
            if not 1 <= roles.count("eligible") <= MAX_ELIGIBLE:
                errors["items"] = "eligible_required"
            elif any(i.item_kind == "service" for i in self.items):
                errors["items"] = "buy_n_pay_m_products_only"
            if self.buy_n is None:
                errors["buy_n"] = "required"
            if self.pay_m is None:
                errors["pay_m"] = "required"
            elif self.buy_n is not None and self.pay_m >= self.buy_n:
                errors["pay_m"] = "must_be_less_than_buy_n"
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            errors["ends_at"] = "must_be_after_start"
        for name in ("starts_at", "ends_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                errors[name] = "timezone_required"
        if errors:
            raise ValueError("; ".join(f"{k}:{v}" for k, v in sorted(errors.items())))
        return self


class OfferItemOut(StrictModel):
    role: str
    item_kind: str
    ref_id: str
    qty: int
    title: str | None = None
    unit_price_ngwee: int | None = None
    available: bool = True


class OfferOut(StrictModel):
    id: str
    vendor_id: str
    offer_type: str
    title: str
    status: OfferStatusOut
    starts_at: datetime | None
    ends_at: datetime | None
    buy_qty: int | None = None
    get_qty: int | None = None
    bundle_pricing: str | None = None
    addon_percent_off: int | None = None
    bundle_price_ngwee: int | None = None
    buy_n: int | None = None
    pay_m: int | None = None
    gift_stock_total: int | None = None
    gift_stock_reserved: int = 0
    gift_stock_available: int | None = None
    max_applications_per_order: int = 1
    per_customer_limit: int | None = None
    paused_by_admin: bool = False
    live: bool = False
    cart_applicable: bool = True
    items: list[OfferItemOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OfferListResponse(StrictModel):
    items: list[OfferOut]
    max_discount_pct: int
    max_active_offers: int


class OfferPreviewLine(StrictModel):
    ref_id: str
    role: str
    qty: int
    list_total_ngwee: int
    final_total_ngwee: int


class OfferPreviewResponse(StrictModel):
    applies: bool
    list_total_ngwee: int
    pay_ngwee: int
    savings_ngwee: int
    gift_qty: int
    gift_value_ngwee: int
    lines: list[OfferPreviewLine]


class AdminOfferPauseRequest(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class OfferBadgeOut(StrictModel):
    offer_id: str
    offer_type: str
    buy_qty: int | None = None
    get_qty: int | None = None
    buy_n: int | None = None
    pay_m: int | None = None
    addon_percent_off: int | None = None
    bundle_pricing: str | None = None


class OfferBadgesResponse(StrictModel):
    badges: dict[str, OfferBadgeOut]


class PublicOfferItemOut(StrictModel):
    role: str
    listing_id: str
    qty: int
    title: str | None = None
    unit_price_ngwee: int
    image_public_id: str | None = None
    product_slug: str | None = None


class PublicOfferOut(StrictModel):
    id: str
    vendor_id: str
    offer_type: str
    title: str
    ends_at: datetime | None = None
    badge: OfferBadgeOut
    items: list[PublicOfferItemOut]
    list_total_ngwee: int
    pay_ngwee: int
    savings_ngwee: int
    gift_qty: int
    gift_value_ngwee: int


class PublicOffersResponse(StrictModel):
    offers: list[PublicOfferOut]
