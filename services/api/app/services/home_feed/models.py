"""Wire + validation models for the home feed and ad placements."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from app.routers.catalog import CatalogListingItem
from app.routers.directory import DirectoryVendorItem
from app.routers.events_public import EventBrowseItem
from app.routers.services_listings import ServiceBrowseItem
from pydantic import BaseModel, Field, field_validator, model_validator

SectionType = Literal[
    "category", "collection", "rule", "services", "events", "vendors", "for_you", "ad_slot"
]
SectionLayout = Literal["rail", "grid", "banner", "ad"]
Audience = Literal["all", "guest", "signed_in"]
RuleSort = Literal["relevance", "newest", "cheapest", "top_rated", "trending"]
ProductClassCode = Literal["A", "B", "C", "D", "E"]
PlacementType = Literal["feed_slot", "carousel_slide"]
AdvertiserKind = Literal["vendor", "business", "external"]
PlacementStatus = Literal["draft", "scheduled", "active", "paused", "ended"]
EffectiveState = Literal["live", "upcoming", "expired", "disabled", "draft", "paused", "ended"]

LOCALE_KEYS = frozenset({"en", "bem", "nya", "fr", "zh"})
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
TITLE_KEY_RE = re.compile(r"^[a-zA-Z0-9_.]{1,120}$")
PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9_./-]{1,255}$")
REFERENCE_RE = re.compile(r"^[-._A-Za-z0-9]{1,80}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

MAX_SECTION_LIMIT = 24
MAX_COLLECTION_IDS = 48
MAX_KEYWORDS = 12


class SectionRule(BaseModel):
    """Rule-based catalogue query. All filters AND together."""

    model_config = {"extra": "forbid"}

    category_paths: list[str] = Field(default_factory=list, max_length=8)
    price_min_ngwee: int | None = Field(default=None, ge=0)
    price_max_ngwee: int | None = Field(default=None, ge=0)
    product_classes: list[ProductClassCode] = Field(default_factory=list, max_length=5)
    conditions: list[Literal["new", "refurbished", "used"]] = Field(default_factory=list)
    min_rating: int | None = Field(default=None, ge=1, le=5)
    keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    new_within_days: int | None = Field(default=None, ge=1, le=365)
    in_stock_only: bool = True
    sort: RuleSort = "relevance"

    @field_validator("category_paths")
    @classmethod
    def _paths(cls, value: list[str]) -> list[str]:
        cleaned = [part.strip().strip("/") for part in value if part.strip()]
        for part in cleaned:
            if not re.fullmatch(r"[a-z0-9][a-z0-9/_-]{0,199}", part):
                raise ValueError("invalid category path")
        return cleaned

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, value: list[str]) -> list[str]:
        cleaned = [word.strip().lower() for word in value if word.strip()]
        for word in cleaned:
            if len(word) > 40:
                raise ValueError("keyword too long")
        return cleaned

    @model_validator(mode="after")
    def _price_range(self) -> SectionRule:
        if (
            self.price_min_ngwee is not None
            and self.price_max_ngwee is not None
            and self.price_max_ngwee < self.price_min_ngwee
        ):
            raise ValueError("price_max_ngwee must be >= price_min_ngwee")
        return self


class SectionConfig(BaseModel):
    model_config = {"extra": "forbid"}

    limit: int = Field(default=12, ge=1, le=MAX_SECTION_LIMIT)
    category_path: str | None = Field(default=None, max_length=200)
    listing_ids: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_IDS)
    rule: SectionRule | None = None
    within_days: int | None = Field(default=None, ge=1, le=60)
    view_all_href: str | None = Field(default=None, max_length=300)

    @field_validator("listing_ids")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        for item in value:
            if not UUID_RE.match(item):
                raise ValueError("listing_ids must be UUIDs")
        return list(dict.fromkeys(value))

    @field_validator("view_all_href")
    @classmethod
    def _href(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_internal_href(value):
            raise ValueError("view_all_href must be an internal path")
        return value


def is_internal_href(value: str) -> bool:
    return value.startswith("/") and not value.startswith("//") and "\\" not in value


def validate_cta_href(value: str, allowed_hosts: frozenset[str]) -> str:
    """Internal route, or https URL on an allow-listed host (exact or subdomain)."""
    value = value.strip()
    if is_internal_href(value):
        return value
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.port:
        raise ValueError("cta_href must be an internal path or an allow-listed https URL")
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts):
        raise ValueError("cta_href host is not on the advertising allow-list")
    return value


def _validate_titles(title_i18n: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for locale, text in title_i18n.items():
        if locale not in LOCALE_KEYS:
            raise ValueError(f"unsupported locale {locale}")
        text = text.strip()
        if not 1 <= len(text) <= 80:
            raise ValueError("titles must be 1-80 characters")
        cleaned[locale] = text
    return cleaned


class SectionBase(BaseModel):
    model_config = {"extra": "forbid"}

    title_key: str | None = None
    title_i18n: dict[str, str] = Field(default_factory=dict)
    layout: SectionLayout = "rail"
    config: SectionConfig = Field(default_factory=SectionConfig)
    position: int = Field(default=0, ge=0, le=100_000)
    enabled: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    audience: Audience = "all"

    @field_validator("title_key")
    @classmethod
    def _title_key(cls, value: str | None) -> str | None:
        if value is not None and not TITLE_KEY_RE.match(value):
            raise ValueError("invalid title_key")
        return value

    @field_validator("title_i18n")
    @classmethod
    def _titles(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_titles(value)


class SectionCreate(SectionBase):
    key: str
    section_type: SectionType

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not KEY_RE.match(value):
            raise ValueError("key must be snake_case, 3-64 chars")
        return value

    @model_validator(mode="after")
    def _consistency(self) -> SectionCreate:
        validate_section_shape(
            self.section_type, self.layout, self.config, self.title_key, self.title_i18n
        )
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class SectionUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    title_key: str | None = None
    title_i18n: dict[str, str] | None = None
    layout: SectionLayout | None = None
    config: SectionConfig | None = None
    position: int | None = Field(default=None, ge=0, le=100_000)
    enabled: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    clear_schedule: bool = False
    audience: Audience | None = None

    @field_validator("title_key")
    @classmethod
    def _title_key(cls, value: str | None) -> str | None:
        if value is not None and not TITLE_KEY_RE.match(value):
            raise ValueError("invalid title_key")
        return value

    @field_validator("title_i18n")
    @classmethod
    def _titles(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return None if value is None else _validate_titles(value)


def validate_section_shape(
    section_type: str,
    layout: str,
    config: SectionConfig,
    title_key: str | None,
    title_i18n: dict[str, str],
) -> None:
    if section_type == "ad_slot":
        if layout != "ad":
            raise ValueError("ad_slot sections must use the ad layout")
        return
    if layout == "ad":
        raise ValueError("only ad_slot sections may use the ad layout")
    if not title_key and not title_i18n:
        raise ValueError("a title_key or per-locale title is required")
    if section_type == "category" and not config.category_path:
        raise ValueError("category sections need config.category_path")
    if section_type == "collection" and not config.listing_ids:
        raise ValueError("collection sections need config.listing_ids")
    if section_type == "rule" and config.rule is None:
        raise ValueError("rule sections need config.rule")


class ReorderRequest(BaseModel):
    model_config = {"extra": "forbid"}

    ordered_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("ordered_ids")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("ordered_ids must be unique")
        for item in value:
            if not UUID_RE.match(item):
                raise ValueError("ordered_ids must be UUIDs")
        return value


class SectionOut(BaseModel):
    id: str
    key: str
    section_type: SectionType
    layout: SectionLayout
    title_key: str | None
    title_i18n: dict[str, str]
    config: dict[str, Any]
    position: int
    enabled: bool
    starts_at: datetime | None
    ends_at: datetime | None
    audience: Audience
    live: bool
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Ads
# ---------------------------------------------------------------------------


class PlacementCreate(BaseModel):
    model_config = {"extra": "forbid"}

    advertiser_kind: AdvertiserKind
    advertiser_vendor_id: str | None = None
    advertiser_name: str = Field(min_length=2, max_length=120)
    placement_type: PlacementType
    image_public_id: str
    headline: str = Field(min_length=2, max_length=120)
    body: str | None = Field(default=None, max_length=280)
    cta_label: str | None = Field(default=None, min_length=1, max_length=40)
    cta_href: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime
    priority: int = Field(default=0, ge=0, le=1000)
    paid_amount_ngwee: int = Field(default=0, ge=0, le=10_000_000_000)
    payment_reference: str | None = None
    enabled: bool = True

    @field_validator("image_public_id")
    @classmethod
    def _public_id(cls, value: str) -> str:
        if not PUBLIC_ID_RE.match(value):
            raise ValueError("invalid Cloudinary public_id")
        return value

    @field_validator("payment_reference")
    @classmethod
    def _reference(cls, value: str | None) -> str | None:
        if value is not None and not REFERENCE_RE.match(value):
            raise ValueError("payment_reference charset is [-._A-Za-z0-9]")
        return value

    @field_validator("advertiser_vendor_id")
    @classmethod
    def _vendor(cls, value: str | None) -> str | None:
        if value is not None and not UUID_RE.match(value):
            raise ValueError("advertiser_vendor_id must be a UUID")
        return value

    @model_validator(mode="after")
    def _consistency(self) -> PlacementCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.advertiser_kind == "vendor" and not self.advertiser_vendor_id:
            raise ValueError("vendor advertisers need advertiser_vendor_id")
        return self


class PlacementUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    advertiser_name: str | None = Field(default=None, min_length=2, max_length=120)
    image_public_id: str | None = None
    headline: str | None = Field(default=None, min_length=2, max_length=120)
    body: str | None = Field(default=None, max_length=280)
    cta_label: str | None = Field(default=None, min_length=1, max_length=40)
    cta_href: str | None = Field(default=None, min_length=1, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    paid_amount_ngwee: int | None = Field(default=None, ge=0, le=10_000_000_000)
    payment_reference: str | None = None
    enabled: bool | None = None

    @field_validator("image_public_id")
    @classmethod
    def _public_id(cls, value: str | None) -> str | None:
        if value is not None and not PUBLIC_ID_RE.match(value):
            raise ValueError("invalid Cloudinary public_id")
        return value

    @field_validator("payment_reference")
    @classmethod
    def _reference(cls, value: str | None) -> str | None:
        if value is not None and not REFERENCE_RE.match(value):
            raise ValueError("payment_reference charset is [-._A-Za-z0-9]")
        return value


class TransitionRequest(BaseModel):
    model_config = {"extra": "forbid"}

    to_status: Literal["scheduled", "active", "paused", "ended", "draft"]
    reason: str | None = Field(default=None, max_length=500)


class PlacementStats(BaseModel):
    impressions: int = 0
    clicks: int = 0
    ctr_bp: int = 0  # click-through in basis points (integer, no floats on reports)


class PlacementOut(BaseModel):
    id: str
    advertiser_kind: AdvertiserKind
    advertiser_vendor_id: str | None
    advertiser_name: str
    placement_type: PlacementType
    image_public_id: str
    headline: str
    body: str | None
    cta_label: str | None
    cta_href: str
    starts_at: datetime
    ends_at: datetime
    priority: int
    paid_amount_ngwee: int
    payment_reference: str | None
    status: PlacementStatus
    enabled: bool
    effective_state: EffectiveState
    stats: PlacementStats = Field(default_factory=PlacementStats)
    updated_at: datetime | None = None


class AdCreativeOut(BaseModel):
    """Public creative — no commercial fields (paid amount/reference never leak)."""

    placement_id: str
    advertiser_name: str
    image_public_id: str
    headline: str
    body: str | None = None
    cta_label: str | None = None
    cta_href: str
    external: bool
    sponsored: bool = True


class AdEvent(BaseModel):
    model_config = {"extra": "ignore"}

    placement_id: str
    kind: Literal["impression", "click"]

    @field_validator("placement_id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not UUID_RE.match(value):
            raise ValueError("placement_id must be a UUID")
        return value


class AdEventBatch(BaseModel):
    model_config = {"extra": "ignore"}

    events: list[AdEvent] = Field(default_factory=list, max_length=20)


class AdEventResult(BaseModel):
    accepted: int
    dropped: int


# ---------------------------------------------------------------------------
# Public feed
# ---------------------------------------------------------------------------


class ForYouExplanation(BaseModel):
    basis: Literal["personal", "trending", "popular"]
    top_categories: list[str] = Field(default_factory=list)


class FeedSectionOut(BaseModel):
    id: str
    key: str
    section_type: SectionType
    layout: SectionLayout
    title: str | None = None
    title_key: str | None = None
    view_all_href: str | None = None
    listings: list[CatalogListingItem] = Field(default_factory=list)
    services: list[ServiceBrowseItem] = Field(default_factory=list)
    events: list[EventBrowseItem] = Field(default_factory=list)
    vendors: list[DirectoryVendorItem] = Field(default_factory=list)
    ad: AdCreativeOut | None = None
    explanation: ForYouExplanation | None = None


class HomeFeedPage(BaseModel):
    sections: list[FeedSectionOut]
    carousel: list[AdCreativeOut] = Field(default_factory=list)
    next_cursor: str | None = None
