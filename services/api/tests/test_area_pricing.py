"""Area-pair delivery pricing: fee formula, bands, rain, rounding, bounds, promise,
multi-vendor consolidation, shadow logging and the seeded tables (real Postgres)."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.errors import AppError
from app.routers.checkout import _match_landmark_zone, area_quote_for_checkout
from app.services.logistics import area_pricing as ap
from app.services.orders.fulfilment import parse_stored_choices, stored_area_fees
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

REPO = Path(__file__).resolve().parents[3]
SEED = REPO / "supabase/migrations/20261113221000_delivery_areas_seed.sql"
ZONE_FEES = {"lusaka_a": 3_000, "lusaka_b": 4_500, "lusaka_c": 6_500}
SETTINGS = ap.AreaPricingSettings()
NO_BOUNDS = ap.FeeBounds(0, 10**9)


def lusaka(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=ap.LUSAKA_TZ)


# 2026-11-18 is a Wednesday; 11-20 Friday; 11-21 Saturday; 11-22 Sunday.
WED = (2026, 11, 18)


def fee_for_km(km: float, *, band: int = 10_000, rain: int = 10_000, pickups: int = 1) -> int:
    return ap.area_fee_ngwee(
        route_metres=int(km * 1000),
        pickups=pickups,
        time_multiplier_bps=band,
        rain_multiplier_bps=rain,
        settings=SETTINGS,
        bounds=NO_BOUNDS,
    )


# ---------------------------------------------------------------------------
# Formula, rounding, bands, rain, bounds
# ---------------------------------------------------------------------------


def test_round_up_to_k5() -> None:
    assert ap.round_up_to_k5(0) == 0
    assert ap.round_up_to_k5(1) == 500
    assert ap.round_up_to_k5(500) == 500
    assert ap.round_up_to_k5(501) == 1_000
    assert ap.round_up_to_k5(2_999) == 3_000
    assert ap.round_up_to_k5(10_001, 10) == 1_500  # ceil(1000.1) -> 1001 -> K15
    with pytest.raises(ValueError):
        ap.round_up_to_k5(-1)


@pytest.mark.parametrize(
    ("km", "expected"),
    [(4, 3_000), (8, 4_500), (13, 6_500), (20, 9_500)],  # blueprint bands K30/K45/K65/K95
)
def test_default_settings_reproduce_the_approved_distance_bands(km: int, expected: int) -> None:
    assert fee_for_km(km) == expected


def test_fee_is_integer_ngwee_and_rounds_up_never_down() -> None:
    # 400 x 4.001 km + 1300 = 2900.4 -> K30, never K29.
    assert fee_for_km(4.001) == 3_000
    fee = fee_for_km(3.3)
    assert isinstance(fee, int) and fee % 500 == 0


def test_time_band_selection_and_boundaries() -> None:
    bands = ap.DEFAULT_TIME_BANDS
    assert ap.time_band_for(7 * 60, bands) == ("morning_peak", 15_000)
    assert ap.time_band_for(9 * 60 - 1, bands) == ("morning_peak", 15_000)
    assert ap.time_band_for(9 * 60, bands) == ("midday", 10_000)
    assert ap.time_band_for(16 * 60 + 30, bands) == ("evening_peak", 12_000)
    assert ap.time_band_for(18 * 60 + 30, bands) == ("evening", 11_000)
    assert ap.time_band_for(21 * 60, bands) == (ap.OFF_PEAK_BAND, 10_000)


def test_bands_and_rain_multiply_the_distance_part_only() -> None:
    # 8 km: 400 x 8 = 3200; x1.2 evening = 3840; + 1300 = 5140 -> K55
    assert fee_for_km(8, band=12_000) == 5_500
    # rain x1.2 on top: 3200 x 1.2 x 1.2 = 4608 + 1300 = 5908 -> K60
    assert fee_for_km(8, band=12_000, rain=12_000) == 6_000
    assert fee_for_km(8, rain=12_000) > fee_for_km(8)


def test_bounds_floor_and_cap() -> None:
    bounds = ap.fee_bounds(SETTINGS, ZONE_FEES, 1)
    assert bounds == ap.FeeBounds(3_000, 6_500)  # cheapest / dearest zone fee
    tiny = ap.area_fee_ngwee(
        route_metres=500,
        pickups=1,
        time_multiplier_bps=10_000,
        rain_multiplier_bps=10_000,
        settings=SETTINGS,
        bounds=bounds,
    )
    assert tiny == 3_000
    far = ap.area_fee_ngwee(
        route_metres=40_000,
        pickups=1,
        time_multiplier_bps=15_000,
        rain_multiplier_bps=12_000,
        settings=SETTINGS,
        bounds=bounds,
    )
    assert far == 6_500
    # Two shops: cap doubles; zone bounds off -> absolute min/max only.
    assert ap.fee_bounds(SETTINGS, ZONE_FEES, 2).cap_ngwee == 13_000
    loose = ap.AreaPricingSettings(zone_bounds=False)
    assert ap.fee_bounds(loose, ZONE_FEES, 1) == ap.FeeBounds(2_500, 20_000)


def test_settings_reject_nonsense_and_parse_falls_back_to_defaults() -> None:
    with pytest.raises(ValueError):
        ap.AreaPricingSettings(min_fee_ngwee=5_000, max_fee_ngwee=1_000)
    with pytest.raises(ValueError):
        ap.AreaPricingSettings(rain_multiplier_bps=9_000)
    parsed = ap.parse_settings({"base_per_km_ngwee": "x", "intra_area_km": "1.5"}, None)
    assert parsed.base_per_km_ngwee == 400
    assert parsed.intra_area_metres == 1_500
    assert parsed.time_bands == ap.DEFAULT_TIME_BANDS
    bad_bands = [{"key": "x", "start": "10:00", "end": "09:00", "multiplier_bps": 10_000}]
    assert ap.parse_time_bands(bad_bands) == ap.DEFAULT_TIME_BANDS
    custom = ap.parse_time_bands(
        [{"key": "rush", "start": "16:00", "end": "18:00", "multiplier_bps": 13_000}]
    )
    assert custom == (ap.TimeBand("rush", 960, 1080, 13_000),)


def test_km_to_metres_uses_decimal() -> None:
    assert ap.km_to_metres("3.15") == 3_150
    assert ap.km_to_metres(2) == 2_000
    assert ap.km_to_metres("-1") is None
    assert ap.km_to_metres(None) is None
    assert ap.km_to_metres(True) is None


# ---------------------------------------------------------------------------
# Promise and cut-off: "Order before 2 pm, get it today"
# ---------------------------------------------------------------------------


def test_cutoff_1359_is_today_and_1401_is_tomorrow() -> None:
    before = ap.delivery_promise(lusaka(*WED, 13, 59), "home")
    after = ap.delivery_promise(lusaka(*WED, 14, 1), "home")
    assert before.day == "today"
    assert (before.window_start, before.window_end) == (time(17, 0), time(19, 30))
    assert after.day == "tomorrow"
    assert (after.window_start, after.window_end) == (time(12, 0), time(14, 30))


def test_cutoff_is_on_the_lusaka_clock_not_utc() -> None:
    # 11:59 UTC is 13:59 in Lusaka (UTC+2): still today.
    assert ap.delivery_promise(datetime(2026, 11, 18, 11, 59, tzinfo=UTC)).day == "today"
    assert ap.delivery_promise(datetime(2026, 11, 18, 12, 1, tzinfo=UTC)).day == "tomorrow"
    with pytest.raises(ValueError):
        ap.delivery_promise(datetime(2026, 11, 18, 12, 0))


def test_work_addresses_stay_inside_office_hours() -> None:
    morning = ap.delivery_promise(lusaka(*WED, 10, 0), "work")
    assert (morning.window_start, morning.window_end) == (time(12, 0), time(14, 30))
    afternoon = ap.delivery_promise(lusaka(*WED, 13, 0), "work")
    assert afternoon.window_end <= time(16, 45)
    rainy = ap.delivery_promise(lusaka(*WED, 13, 0), "work", rain=True)
    assert rainy.window_end == time(16, 45)  # rain never pushes past closing
    home_rain = ap.delivery_promise(lusaka(*WED, 13, 0), "home", rain=True)
    assert home_rain.window_end == time(20, 0)


def test_weekend_rules() -> None:
    fri_late_home = ap.delivery_promise(lusaka(2026, 11, 20, 15, 0), "home")
    assert fri_late_home.day == "tomorrow"
    assert fri_late_home.window_start == time(11, 0)  # Saturday round
    fri_late_work = ap.delivery_promise(lusaka(2026, 11, 20, 15, 0), "work")
    assert fri_late_work.delivery_date.weekday() == 0 and fri_late_work.day == "later"
    sat_early = ap.delivery_promise(lusaka(2026, 11, 21, 9, 30), "home")
    assert sat_early.day == "today"
    sat_late = ap.delivery_promise(lusaka(2026, 11, 21, 10, 30), "home")
    assert sat_late.delivery_date.weekday() == 0
    sunday = ap.delivery_promise(lusaka(2026, 11, 22, 9, 0), "home")
    assert sunday.day == "tomorrow" and sunday.delivery_date.weekday() == 0


# ---------------------------------------------------------------------------
# Routes and the consolidated multi-vendor fee
# ---------------------------------------------------------------------------


def _table(pairs: dict[tuple[str, str], int]) -> dict[tuple[str, str], ap.Leg]:
    table: dict[tuple[str, str], ap.Leg] = {}
    for (a, b), metres in pairs.items():
        table[(a, b)] = ap.Leg(metres, metres // 400)
        table.setdefault((b, a), ap.Leg(metres, metres // 400))
    return table


DIST = _table(
    {
        ("woodlands", "kabulonga"): 3_000,
        ("chilenje", "kabulonga"): 6_000,
        ("matero", "kabulonga"): 12_000,
        ("woodlands", "chilenje"): 4_000,
        ("woodlands", "matero"): 9_000,
        ("chilenje", "matero"): 12_000,
    }
)
WED_MIDDAY = ap.delivery_promise(lusaka(*WED, 10, 0), "home")  # 12:00 window -> midday x1.0


def _quote(vendor_areas: dict[str, str | None], **kw: Any) -> ap.AreaQuote:
    return ap.quote_address(
        customer_area=kw.pop("customer_area", "kabulonga"),
        vendor_areas=vendor_areas,
        distances=DIST,
        settings=kw.pop("settings", SETTINGS),
        zone_fees=ZONE_FEES,
        rain=kw.pop("rain", False),
        promise=kw.pop("promise", WED_MIDDAY),
    )


def test_best_route_tries_every_pickup_order() -> None:
    route = ap.best_route_metres(["matero", "woodlands"], "kabulonga", DIST, SETTINGS)
    # matero -> woodlands -> kabulonga = 9 + 3 = 12 km beats woodlands -> matero -> kabulonga = 21.
    assert route == 12_000
    assert ap.best_route_metres(["woodlands"], "woodlands", DIST, SETTINGS) == 2_000  # intra
    assert ap.best_route_metres(["ngwerere"], "kabulonga", DIST, SETTINGS) is None


def test_multi_vendor_cart_pays_one_consolidated_fee_not_the_sum() -> None:
    single_w = _quote({"v1": "woodlands"})
    single_m = _quote({"v2": "matero"})
    both = _quote({"v1": "woodlands", "v2": "matero"})
    assert single_w.priced and single_m.priced and both.priced
    separate = (single_w.total_fee_ngwee or 0) + (single_m.total_fee_ngwee or 0)
    assert both.total_fee_ngwee is not None and both.total_fee_ngwee < separate
    # 12 km x K4 + 2 stops x K13 = K74 -> K75
    assert both.total_fee_ngwee == 7_500
    assert sum(both.fees_by_vendor.values()) == both.total_fee_ngwee
    assert all(v % 500 == 0 for v in both.fees_by_vendor.values())
    assert both.fees_by_vendor["v2"] > both.fees_by_vendor["v1"]  # the far shop carries more


def test_consolidated_fee_never_exceeds_separate_fees() -> None:
    three = _quote({"v1": "woodlands", "v2": "matero", "v3": "chilenje"})
    parts = [
        _quote({v: a}).total_fee_ngwee or 0
        for v, a in {"v1": "woodlands", "v2": "matero", "v3": "chilenje"}.items()
    ]
    assert three.priced and (three.total_fee_ngwee or 0) <= sum(parts)


def test_quote_reports_why_it_could_not_price() -> None:
    assert _quote({"v1": "woodlands"}, customer_area=None).outcome == "no_customer_area"
    assert _quote({"v1": None}).outcome == "vendor_area_unknown"
    assert _quote({"v1": "ngwerere"}).outcome == "distance_missing"
    assert _quote({}).outcome == "no_delivery_groups"


def test_split_in_k5_units_is_exact() -> None:
    shares = ap.split_in_k5_units(7_500, {"a": 3_000, "b": 6_500})
    assert sum(shares.values()) == 7_500 and all(v % 500 == 0 for v in shares.values())
    assert ap.split_in_k5_units(1_000, {"a": 0, "b": 0}) == {"a": 500, "b": 500}


# ---------------------------------------------------------------------------
# Area matching (picker + landmark fallback stay consistent)
# ---------------------------------------------------------------------------


def _seed_areas() -> list[ap.Area]:
    text = SEED.read_text()
    pattern = re.compile(
        r"\('([a-z0-9_]+)', '((?:[^']|'')+)', '(lusaka_[abc])', (-?[\d.]+), (-?[\d.]+), "
        r"array\[(.*?)\](?:::text\[\])?\)"
    )
    areas = []
    for slug, name, zone, lat, lng, aliases in pattern.findall(text):
        areas.append(
            ap.Area(
                slug,
                name.replace("''", "'"),
                zone,
                float(lat),
                float(lng),
                tuple(re.findall(r"'([^']*)'", aliases)),
            )
        )
    return areas


def test_seed_has_about_sixty_areas_and_matcher_agrees_on_zones() -> None:
    areas = _seed_areas()
    assert 55 <= len(areas) <= 70
    assert len({a.slug for a in areas}) == len(areas)
    for area in areas:
        for term in ap.area_terms(area):
            zone = _match_landmark_zone(term)
            # The landmark matcher either does not know the name or agrees on the band.
            assert zone in (None, area.zone_key), (area.slug, term, zone)


def test_match_area_from_text_whole_word_longest_wins() -> None:
    areas = _seed_areas()
    assert (
        ap.match_area_from_text("House 12, Woodlands Extension", areas) or ap.Area("", "", "", 0, 0)
    ).slug == "woodlands_extension"
    assert (
        ap.match_area_from_text("near Kabulonga shopping centre", areas)
        or ap.Area("", "", "", 0, 0)
    ).slug == "kabulonga"
    assert ap.match_area_from_text("Romantic gardens", areas) is None
    assert ap.nearest_area(-15.4251, 28.3271, areas) is not None
    assert ap.nearest_area(-12.97, 28.63, areas) is None  # Ndola: no Lusaka area


# ---------------------------------------------------------------------------
# Stored quote is fixed for 30 minutes (POST /orders)
# ---------------------------------------------------------------------------


def test_stored_area_quote_is_honoured_within_ttl_and_refused_after() -> None:
    quoted = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    choices = parse_stored_choices(
        [
            {
                "vendor_id": "v1",
                "fulfilment": "delivery",
                "delivery_zone": "lusaka_a",
                "area_fee_ngwee": 3_500,
                "area_quoted_at": quoted.isoformat(),
            },
            {"vendor_id": "v2", "fulfilment": "pickup", "delivery_zone": None},
        ]
    )
    assert stored_area_fees(choices, now=quoted + timedelta(minutes=29), ttl_minutes=30) == {
        "v1": 3_500
    }
    with pytest.raises(AppError) as exc:
        stored_area_fees(choices, now=quoted + timedelta(minutes=31), ttl_minutes=30)
    assert exc.value.code == "orders.fulfilment_not_confirmed"
    plain = parse_stored_choices(
        [{"vendor_id": "v1", "fulfilment": "delivery", "delivery_zone": "lusaka_a"}]
    )
    assert stored_area_fees(plain, now=quoted, ttl_minutes=30) is None
    with pytest.raises(AppError):
        parse_stored_choices(
            [
                {
                    "vendor_id": "v1",
                    "fulfilment": "delivery",
                    "delivery_zone": "lusaka_a",
                    "area_fee_ngwee": -1,
                    "area_quoted_at": quoted.isoformat(),
                }
            ]
        )


# ---------------------------------------------------------------------------
# Shadow mode: compute + log next to the charged fee, charge the old fee
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: FakeStore, table: str) -> None:
        self.store, self.table, self.filters = store, table, []  # type: ignore[var-annotated]
        self.single = False

    def select(self, *_: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.filters.append((column, lambda v, value=value: v == value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self.filters.append((column, lambda v, values=values: v in values))
        return self

    def order(self, *_: Any, **__: Any) -> _Query:
        return self

    def maybe_single(self) -> _Query:
        self.single = True
        return self

    def insert(self, row: dict[str, Any]) -> _Query:
        self.store.inserts.setdefault(self.table, []).append(row)
        return self

    def execute(self) -> _Resp:
        rows = [
            r
            for r in self.store.tables.get(self.table, [])
            if all(check(r.get(col)) for col, check in self.filters)
        ]
        return _Resp((rows[0] if rows else None) if self.single else rows)


class FakeStore:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.inserts: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> _Query:
        return _Query(self, name)


class _Service:
    def __init__(self, store: FakeStore) -> None:
        self.client = store


def _store(**config: Any) -> FakeStore:
    areas = [a for a in _seed_areas() if a.slug in {"woodlands", "kabulonga", "matero"}]
    return FakeStore(
        {
            "platform_config": [{"key": k, "value": v} for k, v in config.items()],
            "areas": [
                {
                    "slug": a.slug,
                    "name": a.name,
                    "zone_key": a.zone_key,
                    "lat": a.lat,
                    "lng": a.lng,
                    "aliases": list(a.aliases),
                    "active": True,
                }
                for a in areas
            ],
            "area_distances": [
                {
                    "from_area": a,
                    "to_area": b,
                    "road_km": f"{leg.metres / 1000:.2f}",
                    "minutes": leg.minutes,
                }
                for (a, b), leg in DIST.items()
            ],
            "vendor_locations": [
                {
                    "vendor_id": "v1",
                    "area": "Woodlands",
                    "lat": None,
                    "lng": None,
                    "is_primary": True,
                },
                {
                    "vendor_id": "v2",
                    "area": None,
                    "lat": -15.3700,
                    "lng": 28.2400,
                    "is_primary": True,
                },
            ],
        }
    )


def test_shadow_mode_computes_and_logs_without_changing_the_charge(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _store()  # defaults: shadow ON, live OFF
    areas = ap.load_areas(store)
    quote, live, promise = area_quote_for_checkout(
        _Service(store),  # type: ignore[arg-type]
        areas=areas,
        customer_area=areas["kabulonga"],
        delivered_vendor_ids=["v1", "v2"],
        zone_fees=ZONE_FEES,
        address_type="home",
        now=lusaka(*WED, 10, 0),
    )
    assert live is False and quote is not None and quote.priced
    assert quote.vendor_areas == {"v1": "woodlands", "v2": "matero"}
    assert promise.day == "today"
    with caplog.at_level(logging.INFO):
        ap.log_quote(
            store,
            quote=quote,
            charged_fee_ngwee=6_000,
            checkout_group_id=str(uuid.uuid4()),
            mode="shadow",
        )
    row = store.inserts["delivery_price_shadow_log"][0]
    assert row["mode"] == "shadow"
    assert row["charged_fee_ngwee"] == 6_000  # what was actually charged (two zone fees)
    assert row["area_fee_ngwee"] == quote.total_fee_ngwee == 7_500
    assert row["pickups"] == 2 and row["route_km"] == "12"
    assert row["customer_area"] == "kabulonga"
    assert "landmark" not in row  # no address text in the log
    assert any(r.message == "checkout.area_pricing_quote" for r in caplog.records)


def test_live_switch_and_off_switch() -> None:
    store = _store(area_pricing_live=True, delivery_rain_mode=True)
    areas = ap.load_areas(store)
    quote, live, _ = area_quote_for_checkout(
        _Service(store),  # type: ignore[arg-type]
        areas=areas,
        customer_area=areas["kabulonga"],
        delivered_vendor_ids=["v1"],
        zone_fees=ZONE_FEES,
        address_type="home",
        now=lusaka(*WED, 10, 0),
    )
    assert live is True and quote is not None and quote.rain is True
    off = _store(area_pricing_shadow=False, area_pricing_live=False)
    quote_off, live_off, promise = area_quote_for_checkout(
        _Service(off),  # type: ignore[arg-type]
        areas=ap.load_areas(off),
        customer_area=None,
        delivered_vendor_ids=["v1"],
        zone_fees=ZONE_FEES,
        address_type="work",
        now=lusaka(*WED, 15, 0),
    )
    assert quote_off is None and live_off is False and promise.day == "tomorrow"


def test_shadow_log_failure_never_breaks_checkout() -> None:
    class Broken(FakeStore):
        def table(self, name: str) -> _Query:
            raise RuntimeError("db down")

    quote = _quote({"v1": "woodlands"})
    ap.log_quote(
        Broken({}), quote=quote, charged_fee_ngwee=3_000, checkout_group_id=None, mode="shadow"
    )


# ---------------------------------------------------------------------------
# Migration: tables, seed, RLS, address columns (disposable Postgres)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    yield conn


def _one(conn: PgConn, sql: str) -> str:
    result = conn.run(sql)
    assert result.ok, result.error
    return result.rows[-1]


def test_migration_seeds_areas_distances_and_settings(db: PgConn) -> None:
    areas = int(_one(db, "SELECT count(*) FROM public.areas WHERE active"))
    pairs = int(_one(db, "SELECT count(*) FROM public.area_distances"))
    assert 55 <= areas <= 70
    assert pairs == areas * (areas - 1)
    assert (
        _one(
            db,
            "SELECT count(*) FROM public.area_distances "
            "WHERE source NOT LIKE 'estimate%refresh with OSRM'",
        )
        == "0"
    )
    assert (
        _one(
            db,
            "SELECT road_km::text FROM public.area_distances "
            "WHERE from_area='woodlands' AND to_area='kabulonga'",
        )
        == "3.15"
    )
    assert (
        _one(db, "SELECT value::text FROM public.platform_config WHERE key='area_pricing_shadow'")
        == "true"
    )
    assert (
        _one(db, "SELECT value::text FROM public.platform_config WHERE key='area_pricing_live'")
        == "false"
    )
    assert (
        _one(db, "SELECT value::text FROM public.platform_config WHERE key='delivery_rain_mode'")
        == "false"
    )
    assert '"14:00"' in _one(
        db, "SELECT value::text FROM public.platform_config WHERE key='delivery_cutoffs'"
    )


def test_rls_areas_public_distances_and_shadow_log_private(db: PgConn) -> None:
    anon_areas = db.run_as("anon", "SELECT count(*) FROM public.areas;")
    assert anon_areas.ok and int(anon_areas.rows[-1]) >= 55
    anon_pairs = db.run_as("anon", "SELECT count(*) FROM public.area_distances;")
    assert not anon_pairs.ok  # no grant to anon
    user = "11111111-1111-1111-1111-111111111111"
    pairs = db.run_as("authenticated", "SELECT count(*) FROM public.area_distances;", user_id=user)
    assert pairs.ok and pairs.rows[-1] == "0"  # RLS: admins only
    log = db.run_as(
        "authenticated", "SELECT count(*) FROM public.delivery_price_shadow_log;", user_id=user
    )
    assert log.ok and log.rows[-1] == "0"
    write = db.run_as(
        "authenticated",
        "INSERT INTO public.areas (slug, name, zone_key, lat, lng) "
        "VALUES ('x_x', 'X', 'lusaka_a', 0, 0);",
        user_id=user,
    )
    assert not write.ok


def test_address_type_is_home_or_work(db: PgConn) -> None:
    bad = db.run(
        "BEGIN; INSERT INTO auth.users (id) "
        "VALUES ('99999999-9999-9999-9999-999999999999') ON CONFLICT DO NOTHING; "
        "INSERT INTO public.addresses (user_id, landmark, address_type) "
        "VALUES ('99999999-9999-9999-9999-999999999999', 'x', 'shop'); ROLLBACK;"
    )
    assert not bad.ok and "addresses_address_type_check" in (bad.error or "")
    good = db.run(
        "BEGIN; INSERT INTO auth.users (id) "
        "VALUES ('99999999-9999-9999-9999-999999999999') ON CONFLICT DO NOTHING; "
        "INSERT INTO public.addresses (user_id, landmark, area_slug, address_type) "
        "VALUES ('99999999-9999-9999-9999-999999999999', 'blue gate', 'kabulonga', 'work') "
        "RETURNING address_type; ROLLBACK;"
    )
    assert good.ok, good.error
