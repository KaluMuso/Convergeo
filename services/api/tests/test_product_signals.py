"""Product signals (docs/plan/product-signals.md): rules, loader and filters."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.core.ttl_cache import clear_ttl_cache_store
from app.routers.catalog import (
    FacetCounts,
    PlpFilterState,
    _CatalogCandidate,
    _ListingRow,
    _SearchDocRow,
    compute_facet_counts,
    decode_plp_filters,
    encode_plp_filters,
    signal_input_from_candidate,
)
from app.services.search.signal_filters import SearchSignalFilters, apply_signal_filters
from app.services.signals import loader
from app.services.signals.models import MarketFacts, SignalInput
from app.services.signals.rules import (
    compute_facts,
    deal_percent,
    market_facts_from_rows,
    ribbon_for,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
LUSAKA = (-15.4167, 28.2833)
KITWE = (-12.8024, 28.2132)


def make_input(**over: Any) -> SignalInput:
    base: dict[str, Any] = {
        "listing_id": "l1",
        "product_id": "p1",
        "vendor_id": "v1",
        "price_ngwee": 10_000,
        "compare_at_ngwee": None,
        "in_stock": True,
        "stock_mode": "always_available",
        "stock_qty": None,
        "fulfilment_mode": "stocked",
        "lead_time_days": None,
        "created_at": NOW - timedelta(days=90),
        "rating": 0.0,
        "review_count": 0,
        "lat": LUSAKA[0],
        "lng": LUSAKA[1],
        "delivery_available": True,
        "vendor_preferred": False,
        "vendor_tier": None,
        "made_in_zambia": False,
    }
    base.update(over)
    return SignalInput(**base)


# --- deal -----------------------------------------------------------------


def test_deal_percent_integer_rounding_and_threshold() -> None:
    assert deal_percent(7_500, 10_000, in_stock=True) == 25
    assert deal_percent(9_500, 10_000, in_stock=True) == 5  # exactly the minimum
    assert deal_percent(9_600, 10_000, in_stock=True) is None  # 4% is noise
    assert deal_percent(9_950, 10_000, in_stock=True) is None
    assert deal_percent(6_667, 10_000, in_stock=True) == 33


def test_deal_requires_stock_and_real_markdown() -> None:
    assert deal_percent(5_000, 10_000, in_stock=False) is None
    assert deal_percent(10_000, 10_000, in_stock=True) is None
    assert deal_percent(12_000, 10_000, in_stock=True) is None
    assert deal_percent(5_000, None, in_stock=True) is None


# --- ribbon ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("preferred", "tier", "expected"),
    [
        (True, 3, "preferred"),
        (True, None, "preferred"),
        (False, 3, "verified_business"),
        (False, 2, "verified_business"),
        (False, 1, "verified_id"),
        (False, None, None),
    ],
)
def test_ribbon_precedence(preferred: bool, tier: int | None, expected: str | None) -> None:
    assert ribbon_for(preferred=preferred, tier=tier) == expected


# --- market / cheapest -----------------------------------------------------


def test_market_counts_distinct_shops_not_listings() -> None:
    facts = market_facts_from_rows([("a", 500), ("a", 450), ("b", 700)])
    assert facts == MarketFacts(seller_count=2, lowest_price_ngwee=450)


def test_cheapest_needs_two_shops() -> None:
    solo = compute_facts(make_input(), market=MarketFacts(1, 10_000), now=NOW)
    assert "cheapest" not in solo.badges_all
    assert solo.seller_count is None  # single seller => no "N shops" line


def test_cheapest_ties_all_win_and_dearer_loses() -> None:
    market = MarketFacts(3, 10_000)
    tie = compute_facts(make_input(price_ngwee=10_000), market=market, now=NOW)
    dearer = compute_facts(make_input(price_ngwee=10_001), market=market, now=NOW)
    assert "cheapest" in tie.badges_all
    assert tie.seller_count == 3 and tie.lowest_price_ngwee == 10_000
    assert "cheapest" not in dearer.badges_all
    assert dearer.seller_count == 3  # still shows "In 3 shops"


def test_out_of_stock_is_never_promoted() -> None:
    out = compute_facts(
        make_input(
            in_stock=False,
            made_in_zambia=True,
            created_at=NOW,
            compare_at_ngwee=20_000,
            rating=5.0,
            review_count=50,
        ),
        market=MarketFacts(2, 10_000),
        now=NOW,
        user_lat=LUSAKA[0],
        user_lng=LUSAKA[1],
    )
    assert out.badges_all == ()
    assert out.deal_percent is None


# --- near you ---------------------------------------------------------------


def test_near_you_requires_location_and_radius() -> None:
    item = make_input()
    assert compute_facts(item, market=None, now=NOW).distance_km is None
    near = compute_facts(item, market=None, now=NOW, user_lat=-15.40, user_lng=28.29)
    assert "near_you" in near.badges_all
    assert near.distance_km is not None and near.distance_km < 5
    far = compute_facts(item, market=None, now=NOW, user_lat=KITWE[0], user_lng=KITWE[1])
    assert "near_you" not in far.badges_all
    assert far.distance_km is not None and far.distance_km > 250


def test_near_you_without_vendor_coordinates_is_omitted() -> None:
    item = make_input(lat=None, lng=None)
    out = compute_facts(item, market=None, now=NOW, user_lat=LUSAKA[0], user_lng=LUSAKA[1])
    assert out.distance_km is None and "near_you" not in out.badges_all


# --- the other badges --------------------------------------------------------


def test_top_rated_needs_volume_and_score() -> None:
    assert (
        "top_rated"
        in compute_facts(make_input(rating=4.5, review_count=5), market=None, now=NOW).badges_all
    )
    assert (
        "top_rated"
        not in compute_facts(
            make_input(rating=5.0, review_count=4), market=None, now=NOW
        ).badges_all
    )
    assert (
        "top_rated"
        not in compute_facts(
            make_input(rating=4.4, review_count=200), market=None, now=NOW
        ).badges_all
    )


def test_new_window_boundaries() -> None:
    assert (
        "new"
        in compute_facts(
            make_input(created_at=NOW - timedelta(days=14)), market=None, now=NOW
        ).badges_all
    )
    assert (
        "new"
        not in compute_facts(
            make_input(created_at=NOW - timedelta(days=15)), market=None, now=NOW
        ).badges_all
    )
    assert "new" not in compute_facts(make_input(created_at=None), market=None, now=NOW).badges_all


def test_low_stock_only_for_tracked_positive_small_counts() -> None:
    def badges(**over: Any) -> tuple[str, ...]:
        return compute_facts(make_input(**over), market=None, now=NOW).badges_all

    assert "low_stock" in badges(stock_mode="tracked", stock_qty=5)
    assert "low_stock" not in badges(stock_mode="tracked", stock_qty=6)
    assert "low_stock" not in badges(stock_mode="tracked", stock_qty=0)
    assert "low_stock" not in badges(stock_mode="always_available", stock_qty=3)


def test_fast_delivery_needs_stocked_lusaka_delivery_and_short_lead() -> None:
    def has(**over: Any) -> bool:
        return "fast_delivery" in compute_facts(make_input(**over), market=None, now=NOW).badges_all

    assert has(lead_time_days=1)
    assert has(lead_time_days=0)
    assert not has(lead_time_days=None)  # unknown is not "fast"
    assert not has(lead_time_days=3)
    assert not has(lead_time_days=1, delivery_available=False)
    assert not has(lead_time_days=1, fulfilment_mode="made_to_order")


def test_made_in_zambia_only_when_approved_flag_set() -> None:
    assert (
        "made_in_zambia"
        in compute_facts(make_input(made_in_zambia=True), market=None, now=NOW).badges_all
    )
    assert "made_in_zambia" not in compute_facts(make_input(), market=None, now=NOW).badges_all


def test_wire_trims_to_two_badges_in_precedence_order() -> None:
    item = make_input(
        made_in_zambia=True,
        rating=4.9,
        review_count=20,
        stock_mode="tracked",
        stock_qty=2,
        created_at=NOW,
        lead_time_days=1,
    )
    facts = compute_facts(
        item, market=MarketFacts(2, 10_000), now=NOW, user_lat=LUSAKA[0], user_lng=LUSAKA[1]
    )
    assert facts.badges_all == (
        "cheapest",
        "near_you",
        "made_in_zambia",
        "top_rated",
        "fast_delivery",
        "low_stock",
        "new",
    )
    wire = facts.to_wire()
    assert wire.badges == ["cheapest", "near_you"]
    assert wire.ribbon is None


# --- loader (fake PostgREST) ---------------------------------------------------


class _Query:
    def __init__(self, rows: list[dict[str, Any]], *, boom: Exception | None = None) -> None:
        self.rows = rows
        self.boom = boom

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self.rows = [r for r in self.rows if r.get(column) in values]
        return self

    def eq(self, column: str, value: Any) -> _Query:
        if "." not in column:  # nested filters (vendors.status) are pre-applied in fixtures
            self.rows = [r for r in self.rows if r.get(column) == value]
        return self

    def execute(self) -> SimpleNamespace:
        if self.boom is not None:
            raise self.boom
        return SimpleNamespace(data=self.rows)


class FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]], *, miz_error: bool = False) -> None:
        self.tables = tables
        self.miz_error = miz_error
        self.calls: list[str] = []

    def table(self, name: str) -> _Query:
        self.calls.append(name)
        rows = list(self.tables.get(name, []))
        return _Query(rows)

    def with_miz(self) -> None:
        pass


def listing_row(
    listing_id: str,
    vendor_id: str,
    price: int,
    *,
    product_id: str = "p1",
    stock_qty: int | None = None,
    stock_mode: str = "always_available",
    preferred: bool = False,
    wholesale: bool = False,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "vendor_id": vendor_id,
        "product_id": product_id,
        "price_ngwee": price,
        "compare_at_ngwee": None,
        "product_class": "A",
        "stock_mode": stock_mode,
        "stock_qty": stock_qty,
        "min_steps": 1,
        "moq": 1,
        "fulfilment_mode": "stocked",
        "lead_time_days": None,
        "vendor_capacity_per_week": None,
        "wholesale": wholesale,
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z",
        "vendors": {
            "id": vendor_id,
            "status": "active",
            "preferred_badge": preferred,
            "vendor_locations": [{"lat": LUSAKA[0], "lng": LUSAKA[1]}],
        },
    }


@pytest.fixture(autouse=True)
def _reset() -> Generator[None, None, None]:
    clear_ttl_cache_store()
    loader._miz_absent_until = 0.0
    yield
    clear_ttl_cache_store()
    loader._miz_absent_until = 0.0


def test_market_excludes_oos_wholesale_and_dedupes_shops() -> None:
    client = FakeClient(
        {
            "vendor_listings": [
                listing_row("l1", "v1", 9_000),
                listing_row("l2", "v1", 8_000),  # same shop, second listing
                listing_row("l3", "v2", 12_000),
                listing_row("l4", "v3", 1_000, stock_mode="tracked", stock_qty=0),  # OOS
                listing_row("l5", "v4", 500, wholesale=True),  # B2B never counts
            ]
        }
    )
    market = loader.load_market_facts(client, ["p1"])["p1"]
    assert market == MarketFacts(seller_count=2, lowest_price_ngwee=8_000)
    # second call is served from the ttl cache: no new vendor_listings read
    before = client.calls.count("vendor_listings")
    loader.load_market_facts(client, ["p1"])
    assert client.calls.count("vendor_listings") == before


def test_listing_signals_end_to_end_with_kyc_ribbon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_ratings", lambda _c, _ids: {"l1": (4.8, 12)})
    client = FakeClient(
        {
            "vendor_listings": [
                listing_row("l1", "v1", 9_000),
                listing_row("l3", "v2", 12_000, preferred=True),
            ],
            # only approved records count; the pending one must not raise a ribbon
            "kyc_records": [
                {"vendor_id": "v1", "tier": 2, "status": "approved"},
                {"vendor_id": "v2", "tier": 3, "status": "pending"},
            ],
        }
    )
    facts = loader.build_signals_for_listing_ids(client, ["L1", "l3"])
    assert facts["l1"].ribbon == "verified_business"
    assert "cheapest" in facts["l1"].badges_all and "top_rated" in facts["l1"].badges_all
    assert facts["l1"].to_wire().seller_count == 2
    assert facts["l3"].ribbon == "preferred"  # preferred badge, not the pending T3
    assert "cheapest" not in facts["l3"].badges_all


def test_bare_vendor_kyc_tier_never_unlocks_a_ribbon() -> None:
    row = listing_row("l1", "v1", 9_000)
    row["vendors"]["kyc_tier"] = 3  # orphaned stored tier, no approved record
    client = FakeClient({"vendor_listings": [row], "kyc_records": []})
    assert loader.build_signals_for_listing_ids(client, ["l1"])["l1"].ribbon is None


def test_made_in_zambia_column_absent_degrades_and_backs_off() -> None:
    class Boom(FakeClient):
        def table(self, name: str) -> _Query:
            self.calls.append(name)
            rows = list(self.tables.get(name, []))
            return _Query(rows, boom=RuntimeError("column does not exist"))

    # only the MiZ probe path should fail; the helper must swallow and back off
    client = Boom({})
    assert loader.load_made_in_zambia_approved(client, ["l1"]) == set()
    calls = len(client.calls)
    assert loader.load_made_in_zambia_approved(client, ["l1"]) == set()
    assert len(client.calls) == calls  # backed off: no second failing probe


def test_made_in_zambia_approved_rows_are_returned() -> None:
    client = FakeClient(
        {
            "vendor_listings": [
                {"id": "l1", "made_in_zambia_status": "approved"},
                {"id": "l2", "made_in_zambia_status": "claimed"},
            ]
        }
    )
    assert loader.load_made_in_zambia_approved(client, ["l1", "l2"]) == {"l1"}


def test_signals_outage_returns_empty_not_an_error() -> None:
    class Down:
        def table(self, _name: str) -> Any:
            raise RuntimeError("db down")

    assert loader.build_signals_for_listing_ids(Down(), ["l1"]) == {}
    assert loader.build_signals_for_product_ids(Down(), ["p1"]) == {}


def test_product_signals_use_cheapest_in_stock_seller_and_drop_cheapest_badge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader, "_ratings", lambda _c, _ids: {})
    client = FakeClient(
        {
            "vendor_listings": [
                listing_row("l1", "v1", 9_000),
                listing_row("l3", "v2", 7_000),
                listing_row("l4", "v3", 100, stock_mode="tracked", stock_qty=0),
            ],
            "kyc_records": [{"vendor_id": "v2", "tier": 1, "status": "approved"}],
        }
    )
    facts = loader.build_signals_for_product_ids(client, ["P1"])["p1"]
    assert facts.seller_count == 2 and facts.lowest_price_ngwee == 7_000
    assert facts.ribbon == "verified_id"
    assert "cheapest" not in facts.badges_all


# --- catalog candidates / filters ----------------------------------------------


def candidate(
    listing_id: str,
    *,
    vendor_tier: int | None = None,
    preferred: bool = False,
    compare_at: int | None = None,
    price: int = 10_000,
    miz: bool = False,
    rating: float = 0.0,
    in_stock: bool = True,
) -> _CatalogCandidate:
    return _CatalogCandidate(
        search_doc=_SearchDocRow(
            entity_id=listing_id,
            title=f"Cup {listing_id}",
            price_min_ngwee=price,
            lat=LUSAKA[0],
            lng=LUSAKA[1],
        ),
        listing=_ListingRow(
            id=listing_id,
            vendor_id=f"v-{listing_id}",
            product_id="p1",
            condition="new",
            stock_mode="always_available",
            compare_at_ngwee=compare_at,
            created_at="2026-11-20T00:00:00Z",
        ),
        vendor={"id": f"v-{listing_id}", "preferred_badge": preferred},
        product=None,
        image_public_id=None,
        landmark=None,
        rating=rating,
        review_count=10 if rating else 0,
        in_stock=in_stock,
        vendor_tier=vendor_tier,
        made_in_zambia=miz,
    )


def test_catalog_filters_round_trip_through_url_params() -> None:
    on_params = {"verified": "1", "deals": "true", "made_in_zambia": "yes"}
    state = decode_plp_filters(cast(dict[str, str | list[str] | None], on_params))
    assert state.verified and state.deals and state.made_in_zambia
    encoded = encode_plp_filters(state)
    assert encoded["verified"] == "1" and encoded["deals"] == "1"
    assert decode_plp_filters(cast(dict[str, str | list[str] | None], encoded)) == state
    off = decode_plp_filters(cast(dict[str, str | list[str] | None], {"verified": "0"}))
    assert not off.verified
    assert "verified" not in encode_plp_filters(off)


def test_catalog_signal_facets_and_filtering() -> None:
    rows = [
        candidate("a", vendor_tier=2, compare_at=20_000),
        candidate("b", preferred=True),
        candidate("c", compare_at=20_000, in_stock=False),  # OOS: not a deal
        candidate("d", miz=True),
    ]
    facets: FacetCounts = compute_facet_counts(rows, PlpFilterState())
    counts = {b.value: b.count for b in facets.signals}
    assert counts == {"verified": 2, "deals": 1, "made_in_zambia": 1}

    from app.routers.catalog import _matches_filters

    verified = [r for r in rows if _matches_filters(r, filters=PlpFilterState(verified=True))]
    assert [r.listing.id for r in verified] == ["a", "b"]
    deals = [r for r in rows if _matches_filters(r, filters=PlpFilterState(deals=True))]
    assert [r.listing.id for r in deals] == ["a"]


def test_made_in_zambia_facet_hidden_until_a_claim_is_approved() -> None:
    facets = compute_facet_counts([candidate("a")], PlpFilterState())
    assert "made_in_zambia" not in {b.value for b in facets.signals}


def test_candidate_signal_input_uses_approved_tier_not_vendor_row() -> None:
    row = candidate("a", vendor_tier=None)
    row.vendor["kyc_tier"] = 3
    assert signal_input_from_candidate(row).vendor_tier is None


# --- search filters ---------------------------------------------------------------


def _hit(
    kind: str, entity_id: str, lat: float | None = LUSAKA[0], lng: float | None = LUSAKA[1]
) -> Any:
    return SimpleNamespace(entity_kind=kind, entity_id=entity_id, lat=lat, lng=lng)


def test_search_filters_combine_and_drop_non_product_kinds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_ratings", lambda _c, _ids: {"l1": (4.6, 9)})
    client = FakeClient(
        {
            "vendor_listings": [
                {**listing_row("l1", "v1", 9_000), "compare_at_ngwee": 20_000},
                listing_row("l2", "v2", 9_000),
            ],
            "kyc_records": [{"vendor_id": "v1", "tier": 2, "status": "approved"}],
        }
    )
    hits = [_hit("listing", "l1"), _hit("listing", "l2"), _hit("event", "e1")]
    flt = SearchSignalFilters(verified=True, deals=True, in_stock=True, min_rating=4)
    kept = apply_signal_filters(client, hits, flt, user_lat=None, user_lng=None)
    assert [h.entity_id for h in kept] == ["l1"]
    assert (
        apply_signal_filters(client, hits, SearchSignalFilters(), user_lat=None, user_lng=None)
        == hits
    )


def test_search_near_me_filter_needs_location_and_hit_coordinates() -> None:
    client = FakeClient({"vendor_listings": [listing_row("l1", "v1", 9_000)], "kyc_records": []})
    flt = SearchSignalFilters(radius_km=5)
    hits = [_hit("listing", "l1")]
    assert apply_signal_filters(client, hits, flt, user_lat=None, user_lng=None) == []
    kept = apply_signal_filters(client, hits, flt, user_lat=-15.40, user_lng=28.29)
    assert len(kept) == 1
    far = apply_signal_filters(client, hits, flt, user_lat=KITWE[0], user_lng=KITWE[1])
    assert far == []
    no_geo = [_hit("listing", "l1", lat=None, lng=None)]
    assert apply_signal_filters(client, no_geo, flt, user_lat=-15.40, user_lng=28.29) == []


def test_search_filters_fail_closed_when_signals_unavailable() -> None:
    class Down:
        def table(self, _name: str) -> Any:
            raise RuntimeError("db down")

    kept = apply_signal_filters(
        Down(),
        [_hit("listing", "l1")],
        SearchSignalFilters(verified=True),
        user_lat=None,
        user_lng=None,
    )
    assert kept == []
