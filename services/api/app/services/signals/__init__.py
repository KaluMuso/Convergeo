"""Product signals: badges, ribbons and market facts for listing cards.

See ``docs/plan/product-signals.md``. Pure rules live in :mod:`.rules`; the
batched, fail-soft data loading in :mod:`.loader`.
"""

from app.services.signals.loader import (
    attach_catalog_signals,
    build_signals_for_listing_ids,
    build_signals_for_product_ids,
)
from app.services.signals.models import (
    SIGNAL_BADGE_ORDER,
    ListingSignals,
    SignalBadge,
    SignalRibbon,
)

__all__ = [
    "SIGNAL_BADGE_ORDER",
    "ListingSignals",
    "SignalBadge",
    "SignalRibbon",
    "attach_catalog_signals",
    "build_signals_for_listing_ids",
    "build_signals_for_product_ids",
]
