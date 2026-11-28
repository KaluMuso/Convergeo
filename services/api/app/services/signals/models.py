from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SignalBadge = Literal[
    "cheapest",
    "near_you",
    "made_in_zambia",
    "top_rated",
    "fast_delivery",
    "low_stock",
    "new",
]
SignalRibbon = Literal["preferred", "verified_business", "verified_id"]

#: Badge precedence, highest first. The wire list is this order, trimmed to
#: :data:`MAX_BADGES`. ``deal`` is deliberately absent: it is carried as
#: ``deal_percent`` and shown by the card's existing discount chip.
SIGNAL_BADGE_ORDER: tuple[SignalBadge, ...] = (
    "cheapest",
    "near_you",
    "made_in_zambia",
    "top_rated",
    "fast_delivery",
    "low_stock",
    "new",
)
MAX_BADGES = 2

# Tunables (documented in docs/plan/product-signals.md).
NEAR_YOU_KM = 5.0
NEW_WINDOW_DAYS = 14
TOP_RATED_MIN_REVIEWS = 5
TOP_RATED_MIN_RATING = 4.5
LOW_STOCK_MAX_QTY = 5
DEAL_MIN_PERCENT = 5
FAST_DELIVERY_MAX_LEAD_DAYS = 1


class ListingSignals(BaseModel):
    """Public wire contract; attached to listing cards, search hits, comparison rows."""

    #: At most one KYC / trust ribbon.
    ribbon: SignalRibbon | None = None
    #: At most two badges, already in precedence order.
    badges: list[SignalBadge] = Field(default_factory=list)
    #: Distinct shops with this canonical product in stock (null when fewer than 2).
    seller_count: int | None = None
    #: Lowest in-stock price among those shops, ngwee (with ``seller_count``).
    lowest_price_ngwee: int | None = None
    #: Whole-percent saving vs compare-at (null below the minimum threshold).
    deal_percent: int | None = None
    #: Distance from the shopper's chosen point; only when a location was supplied.
    distance_km: float | None = None


@dataclass(frozen=True, slots=True)
class SignalInput:
    """Everything the rules need about one listing (no I/O)."""

    listing_id: str
    product_id: str | None
    vendor_id: str
    price_ngwee: int
    compare_at_ngwee: int | None
    in_stock: bool
    stock_mode: str
    stock_qty: int | None
    fulfilment_mode: str
    lead_time_days: int | None
    created_at: datetime | None
    rating: float
    review_count: int
    lat: float | None
    lng: float | None
    delivery_available: bool
    vendor_preferred: bool
    #: Highest *approved* kyc_records tier (never the bare ``vendors.kyc_tier``).
    vendor_tier: int | None
    made_in_zambia: bool


@dataclass(frozen=True, slots=True)
class MarketFacts:
    seller_count: int
    lowest_price_ngwee: int | None


@dataclass(frozen=True, slots=True)
class SignalFacts:
    """Full rule outcome; the wire model is a trimmed projection, filters use this."""

    ribbon: SignalRibbon | None
    badges_all: tuple[SignalBadge, ...]
    seller_count: int | None
    lowest_price_ngwee: int | None
    deal_percent: int | None
    distance_km: float | None
    verified: bool
    made_in_zambia: bool
    in_stock: bool = False
    rating: float = 0.0
    review_count: int = 0

    def to_wire(self) -> ListingSignals:
        return ListingSignals(
            ribbon=self.ribbon,
            badges=list(self.badges_all[:MAX_BADGES]),
            seller_count=self.seller_count,
            lowest_price_ngwee=self.lowest_price_ngwee,
            deal_percent=self.deal_percent,
            distance_km=self.distance_km,
        )
