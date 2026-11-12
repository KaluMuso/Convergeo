"""Server-side resolution of admin-defined home feed sections.

One request builds the catalogue candidate set at most once and resolves every
section of the page against it in memory (no N+1 per section). Sections that
resolve to no data are skipped, so the client only ever receives renderable
sections. Ads are interleaved by ``ad_slot`` sections; the n-th live ad slot in
the full ordered sequence receives the n-th live ``feed_slot`` placement
(priority desc, then earliest start). Disabled / out-of-window placements are
filtered here and therefore vanish from every customer surface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.routers.catalog import (
    CatalogCandidate,
    build_catalog_candidates,
    catalog_item_from_candidate,
)
from app.services.catalog_visibility import active_vendor_ids, visible_target_keys
from app.services.home_feed.models import (
    AdCreativeOut,
    FeedSectionOut,
    ForYouExplanation,
    HomeFeedPage,
    SectionConfig,
    SectionRule,
    is_internal_href,
)
from app.services.home_feed.personalization import load_user_signals, rank_for_you

logger = logging.getLogger(__name__)

SECTION_COLUMNS = (
    "id, key, section_type, layout, title_key, title_i18n, config, position, enabled, "
    "starts_at, ends_at, audience, updated_at"
)
PLACEMENT_COLUMNS = (
    "id, advertiser_kind, advertiser_vendor_id, advertiser_name, placement_type, "
    "image_public_id, headline, body, cta_label, cta_href, starts_at, ends_at, priority, "
    "paid_amount_ngwee, payment_reference, status, enabled, updated_at, target_kind, target_id"
)
LIVE_STATUSES = frozenset({"scheduled", "active"})
CURSOR_PREFIX = "v1."
DEFAULT_PAGE_SIZE = 4
MAX_PAGE_SIZE = 8
MAX_CAROUSEL_SPONSORED = 3
TRENDING_FETCH_LIMIT = 24


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def encode_cursor(offset: int) -> str:
    return f"{CURSOR_PREFIX}{offset}"


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    if not cursor.startswith(CURSOR_PREFIX):
        raise ValueError("invalid cursor")
    raw = cursor[len(CURSOR_PREFIX) :]
    if not raw.isdigit() or len(raw) > 4:
        raise ValueError("invalid cursor")
    return int(raw)


# ---------------------------------------------------------------------------
# Visibility predicates
# ---------------------------------------------------------------------------


def section_is_live(row: dict[str, Any], *, now: datetime, signed_in: bool) -> bool:
    if not bool(row.get("enabled", True)):
        return False
    starts_at = parse_ts(row.get("starts_at"))
    ends_at = parse_ts(row.get("ends_at"))
    if starts_at is not None and now < starts_at:
        return False
    if ends_at is not None and now >= ends_at:
        return False
    audience = str(row.get("audience") or "all")
    if audience == "guest" and signed_in:
        return False
    if audience == "signed_in" and not signed_in:
        return False
    return True


def placement_is_live(row: dict[str, Any], *, now: datetime) -> bool:
    if not bool(row.get("enabled", False)):
        return False
    if str(row.get("status")) not in LIVE_STATUSES:
        return False
    starts_at = parse_ts(row.get("starts_at"))
    ends_at = parse_ts(row.get("ends_at"))
    if starts_at is None or ends_at is None:
        return False
    return starts_at <= now < ends_at


def placement_effective_state(row: dict[str, Any], *, now: datetime) -> str:
    status = str(row.get("status"))
    if status in {"draft", "paused", "ended"}:
        return status
    if not bool(row.get("enabled", False)):
        return "disabled"
    starts_at = parse_ts(row.get("starts_at"))
    ends_at = parse_ts(row.get("ends_at"))
    if ends_at is not None and now >= ends_at:
        return "expired"
    if starts_at is not None and now < starts_at:
        return "upcoming"
    return "live"


def to_creative(row: dict[str, Any]) -> AdCreativeOut:
    href = str(row["cta_href"])
    return AdCreativeOut(
        placement_id=str(row["id"]),
        advertiser_name=str(row["advertiser_name"]),
        image_public_id=str(row["image_public_id"]),
        headline=str(row["headline"]),
        body=row.get("body"),
        cta_label=row.get("cta_label"),
        cta_href=href,
        external=not is_internal_href(href),
    )


def _placement_order(row: dict[str, Any]) -> tuple[int, str, str]:
    return (-int(row.get("priority") or 0), str(row.get("starts_at") or ""), str(row["id"]))


def load_sections(client: Any) -> list[dict[str, Any]]:
    return _rows(
        client.table("home_feed_sections")
        .select(SECTION_COLUMNS)
        .eq("enabled", True)
        .order("position", desc=False)
        .execute()
    )


def load_live_placements(client: Any, *, now: datetime) -> list[dict[str, Any]]:
    rows = _rows(
        client.table("ad_placements")
        .select(PLACEMENT_COLUMNS)
        .eq("enabled", True)
        .in_("status", sorted(LIVE_STATUSES))
        .execute()
    )
    live = [row for row in rows if placement_is_live(row, now=now)]
    live = filter_placements_with_visible_targets(client, live)
    live.sort(key=_placement_order)
    return live


def filter_placements_with_visible_targets(
    client: Any, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop placements whose target or advertiser vendor customers can no longer see.

    A placement can stay ``active`` while the thing it promotes is hidden,
    blocked, removed or its vendor suspended; it must vanish from every surface
    in that case. Fails closed: if visibility cannot be read, targeted and
    vendor-advertiser placements are dropped (house/external ads still serve).
    """
    if not rows:
        return rows
    refs = {
        (str(row["target_kind"]), str(row["target_id"]))
        for row in rows
        if row.get("target_kind") and row.get("target_id")
    }
    vendor_ids = {
        str(row["advertiser_vendor_id"])
        for row in rows
        if row.get("advertiser_kind") == "vendor" and row.get("advertiser_vendor_id")
    }
    try:
        visible = visible_target_keys(client, refs) if refs else set()
        vendors = active_vendor_ids(client, vendor_ids) if vendor_ids else set()
    except Exception:
        logger.warning("home_feed_target_visibility_failed", exc_info=True)
        visible, vendors = set(), set()
    kept: list[dict[str, Any]] = []
    for row in rows:
        if row.get("target_kind") and row.get("target_id"):
            if (str(row["target_kind"]), str(row["target_id"])) not in visible:
                continue
        if row.get("advertiser_kind") == "vendor":
            if str(row.get("advertiser_vendor_id")) not in vendors:
                continue
        kept.append(row)
    return kept


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


def _in_paths(path: str | None, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    if not path:
        return False
    clean = path.strip("/")
    return any(clean == prefix or clean.startswith(f"{prefix}/") for prefix in prefixes)


def apply_rule(
    candidates: list[CatalogCandidate],
    rule: SectionRule,
    *,
    now: datetime,
    trending_ids: list[str] | None = None,
) -> list[CatalogCandidate]:
    keywords = [word.lower() for word in rule.keywords]
    new_since = now - timedelta(days=rule.new_within_days) if rule.new_within_days else None

    def matches(row: CatalogCandidate) -> bool:
        price = row.search_doc.price_min_ngwee or 0
        if rule.in_stock_only and not row.in_stock:
            return False
        if not _in_paths(row.search_doc.category_path, rule.category_paths):
            return False
        if rule.price_min_ngwee is not None and price < rule.price_min_ngwee:
            return False
        if rule.price_max_ngwee is not None and price > rule.price_max_ngwee:
            return False
        if rule.product_classes and row.listing.product_class not in rule.product_classes:
            return False
        if rule.conditions and row.listing.condition not in rule.conditions:
            return False
        if rule.min_rating is not None and row.rating < rule.min_rating:
            return False
        if keywords:
            title = row.search_doc.title.lower()
            if not any(word in title for word in keywords):
                return False
        if new_since is not None:
            created = parse_ts(row.listing.created_at)
            if created is None or created < new_since:
                return False
        return True

    pool = [row for row in candidates if matches(row)]
    return sort_candidates(pool, rule.sort, trending_ids=trending_ids)


def _relevance_key(row: CatalogCandidate) -> tuple[int, int, str]:
    boost = row.search_doc.boost_signals
    return (
        1 if boost.get("verified") else 0,
        1 if row.in_stock else 0,
        row.search_doc.updated_at or "",
    )


def sort_candidates(
    pool: list[CatalogCandidate],
    sort: str,
    *,
    trending_ids: list[str] | None = None,
) -> list[CatalogCandidate]:
    if sort == "newest":
        return sorted(pool, key=lambda row: row.listing.created_at or "", reverse=True)
    if sort == "cheapest":
        return sorted(pool, key=lambda row: (row.search_doc.price_min_ngwee or 0, row.listing.id))
    if sort == "top_rated":
        return sorted(
            pool,
            key=lambda row: (row.rating, row.review_count, _relevance_key(row)),
            reverse=True,
        )
    if sort == "trending":
        rank = {listing_id: index for index, listing_id in enumerate(trending_ids or [])}
        return sorted(
            (row for row in pool if row.listing.id in rank), key=lambda row: rank[row.listing.id]
        )
    return sorted(pool, key=_relevance_key, reverse=True)


# ---------------------------------------------------------------------------
# Context (lazy, per request)
# ---------------------------------------------------------------------------


class FeedContext:
    def __init__(
        self,
        client: Any,
        *,
        now: datetime,
        locale: str,
        user_id: str | None,
        candidate_loader: Callable[[Any], list[CatalogCandidate]] | None = None,
    ) -> None:
        self.client = client
        self.now = now
        self.locale = locale
        self.user_id = user_id
        self._candidate_loader = candidate_loader or (lambda c: build_catalog_candidates(c))
        self._candidates: list[CatalogCandidate] | None = None
        self._trending: list[str] | None = None

    @property
    def candidates(self) -> list[CatalogCandidate]:
        if self._candidates is None:
            try:
                self._candidates = self._candidate_loader(self.client)
            except Exception:
                logger.warning("home_feed_candidates_failed", exc_info=True)
                self._candidates = []
        return self._candidates

    @property
    def trending_ids(self) -> list[str]:
        if self._trending is None:
            try:
                from app.services.discovery.trending import fetch_trending_listings

                self._trending = [
                    item.listing_id
                    for item in fetch_trending_listings(self.client, limit=TRENDING_FETCH_LIMIT)
                ]
            except Exception:
                logger.warning("home_feed_trending_failed", exc_info=True)
                self._trending = []
        return self._trending


def resolve_title(row: dict[str, Any], locale: str) -> str | None:
    titles = row.get("title_i18n")
    if isinstance(titles, dict):
        value = titles.get(locale) or titles.get("en")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _view_all(config: SectionConfig, row: dict[str, Any]) -> str | None:
    if config.view_all_href:
        return config.view_all_href
    if row.get("section_type") == "category" and config.category_path:
        return f"/c/{config.category_path}"
    return None


def _base(row: dict[str, Any], config: SectionConfig, locale: str) -> FeedSectionOut:
    return FeedSectionOut(
        id=str(row["id"]),
        key=str(row["key"]),
        section_type=row["section_type"],
        layout=row.get("layout") or "rail",
        title=resolve_title(row, locale),
        title_key=row.get("title_key"),
        view_all_href=_view_all(config, row),
    )


def _listing_section(
    out: FeedSectionOut, pool: list[CatalogCandidate], limit: int
) -> FeedSectionOut | None:
    items = [catalog_item_from_candidate(row) for row in pool[:limit]]
    if not items:
        return None
    out.listings = items
    return out


def resolve_section(
    ctx: FeedContext,
    row: dict[str, Any],
    *,
    ad: dict[str, Any] | None = None,
) -> FeedSectionOut | None:
    """Resolve one section; ``None`` when it has nothing to show."""
    try:
        config = SectionConfig.model_validate(row.get("config") or {})
    except Exception:
        logger.warning("home_feed_bad_config", extra={"section": row.get("key")})
        return None
    out = _base(row, config, ctx.locale)
    section_type = row.get("section_type")
    limit = config.limit

    if section_type == "ad_slot":
        if ad is None:
            return None
        out.ad = to_creative(ad)
        return out

    if section_type == "category":
        rule = SectionRule(category_paths=[config.category_path or ""], sort="relevance")
        return _listing_section(out, apply_rule(ctx.candidates, rule, now=ctx.now), limit)

    if section_type == "rule" and config.rule is not None:
        trending = ctx.trending_ids if config.rule.sort == "trending" else None
        pool = apply_rule(ctx.candidates, config.rule, now=ctx.now, trending_ids=trending)
        return _listing_section(out, pool, limit)

    if section_type == "collection":
        by_id = {row_.listing.id: row_ for row_ in ctx.candidates}
        pool = [by_id[item] for item in config.listing_ids if item in by_id]
        return _listing_section(out, pool, limit)

    if section_type == "for_you":
        return _resolve_for_you(ctx, out, limit)

    if section_type == "services":
        from app.routers.services_listings import build_browse_response as services_browse

        try:
            out.services = services_browse(ctx.client).items[:limit]
        except Exception:
            logger.warning("home_feed_services_failed", exc_info=True)
            return None
        return out if out.services else None

    if section_type == "events":
        from app.routers.events_public import build_browse_response as events_browse

        horizon = ctx.now + timedelta(days=config.within_days or 7)
        try:
            items = events_browse(ctx.client).items
        except Exception:
            logger.warning("home_feed_events_failed", exc_info=True)
            return None
        upcoming = [
            item
            for item in items
            if item.next_starts_at is not None
            and ctx.now <= item.next_starts_at.astimezone(UTC) <= horizon
            and not item.is_sold_out
        ]
        upcoming.sort(key=lambda item: item.next_starts_at or ctx.now)
        out.events = upcoming[:limit]
        return out if out.events else None

    if section_type == "vendors":
        from app.routers.directory import list_directory_vendors

        try:
            vendors = list_directory_vendors(ctx.client, page_size=max(limit, 12)).items
        except Exception:
            logger.warning("home_feed_vendors_failed", exc_info=True)
            return None
        ranked = sorted(
            vendors, key=lambda v: ((v.rating_avg or 0.0), v.rating_count), reverse=True
        )
        out.vendors = ranked[:limit]
        return out if out.vendors else None

    return None


def _resolve_for_you(ctx: FeedContext, out: FeedSectionOut, limit: int) -> FeedSectionOut | None:
    candidates = ctx.candidates
    if ctx.user_id:
        signals = load_user_signals(ctx.client, ctx.user_id, now=ctx.now)
        ranked = rank_for_you(candidates, signals)
        if ranked.personal:
            out.explanation = ForYouExplanation(
                basis="personal", top_categories=ranked.top_categories
            )
            return _listing_section(out, ranked.candidates, limit)
    trending = sort_candidates(
        [row for row in candidates if row.in_stock], "trending", trending_ids=ctx.trending_ids
    )
    if trending:
        out.explanation = ForYouExplanation(basis="trending")
        return _listing_section(out, trending, limit)
    popular = sort_candidates([row for row in candidates if row.in_stock], "top_rated")
    out.explanation = ForYouExplanation(basis="popular")
    return _listing_section(out, popular, limit)


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------


def build_feed_page(
    client: Any,
    *,
    cursor: str | None,
    page_size: int = DEFAULT_PAGE_SIZE,
    locale: str = "en",
    user_id: str | None = None,
    now: datetime | None = None,
    candidate_loader: Callable[[Any], list[CatalogCandidate]] | None = None,
) -> HomeFeedPage:
    reference = now or datetime.now(UTC)
    offset = decode_cursor(cursor)
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    signed_in = user_id is not None

    sections = [
        row
        for row in load_sections(client)
        if section_is_live(row, now=reference, signed_in=signed_in)
    ]
    try:
        placements = load_live_placements(client, now=reference)
    except Exception:
        logger.warning("home_feed_placements_failed", exc_info=True)
        placements = []
    feed_ads = [row for row in placements if row.get("placement_type") == "feed_slot"]

    # Global ad-slot ordinal so assignment is stable across pages.
    ad_for_index: dict[int, dict[str, Any]] = {}
    ordinal = 0
    for index, row in enumerate(sections):
        if row.get("section_type") == "ad_slot":
            if ordinal < len(feed_ads):
                ad_for_index[index] = feed_ads[ordinal]
            ordinal += 1

    ctx = FeedContext(
        client, now=reference, locale=locale, user_id=user_id, candidate_loader=candidate_loader
    )
    resolved: list[FeedSectionOut] = []
    index = offset
    while index < len(sections) and len(resolved) < size:
        section = resolve_section(ctx, sections[index], ad=ad_for_index.get(index))
        if section is not None:
            resolved.append(section)
        index += 1

    carousel: list[AdCreativeOut] = []
    if offset == 0:
        carousel = [
            to_creative(row) for row in placements if row.get("placement_type") == "carousel_slide"
        ][:MAX_CAROUSEL_SPONSORED]

    return HomeFeedPage(
        sections=resolved,
        carousel=carousel,
        next_cursor=encode_cursor(index) if index < len(sections) else None,
    )
