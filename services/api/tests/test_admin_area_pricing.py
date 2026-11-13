"""Admin editing of the area-pair price table, and where the fee is booked.

* ``/admin/logistics/area-pricing/settings`` (GET / PUT): per-km rate, stop fee,
  bounds, rain multiplier, quote TTL, time bands. Integer ngwee / bps only.
* ``/admin/logistics/areas`` and ``/admin/logistics/area-distances`` (GET / PATCH):
  hand corrections to the distance table, marked ``manual_override``.
* An area-pair share is charged as the group's delivery fee, so it reaches
  ``delivery_revenue`` through the same ledger templates as the zone fee.
"""

from __future__ import annotations

import copy
from collections.abc import Generator
from datetime import date, time
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import admin_permission_for_request
from app.core.ratelimit_policies import POLICIES
from app.main import create_app
from app.services.ledger.templates import delivery_fee_capture, delivery_fee_vendor_charge
from app.services.logistics import area_pricing as ap
from app.services.logistics.delivery_pricing import (
    AutoFreeDeliveryPolicy,
    PricingLine,
    VendorDeliveryTerms,
    price_delivery_groups,
)
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
TOKEN = {"Authorization": "Bearer valid.jwt.token"}
SETTINGS_URL = "/admin/logistics/area-pricing/settings"

DEFAULT_BODY: dict[str, Any] = {
    "base_per_km_ngwee": 400,
    "stop_fee_ngwee": 1300,
    "intra_area_metres": 2000,
    "min_fee_ngwee": 2500,
    "max_fee_ngwee": 20000,
    "rain_multiplier_bps": 12000,
    "zone_bounds": True,
    "quote_ttl_minutes": 30,
    "time_bands": [
        {"key": "morning_peak", "start": "07:00", "end": "09:00", "multiplier_bps": 15000},
        {"key": "midday", "start": "09:00", "end": "16:30", "multiplier_bps": 10000},
        {"key": "evening_peak", "start": "16:30", "end": "18:30", "multiplier_bps": 12000},
        {"key": "evening", "start": "18:30", "end": "20:00", "multiplier_bps": 11000},
    ],
}


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: Store, table: str) -> None:
        self.store, self.table = store, table
        self.filters: list[tuple[str, Any]] = []
        self.upserting: list[dict[str, Any]] | None = None
        self.conflict: list[str] = []

    def select(self, *_: Any) -> _Query:
        return self

    def order(self, *_: Any, **__: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.filters.append((column, lambda v, value=value: v == value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self.filters.append((column, lambda v, values=values: v in values))
        return self

    def upsert(self, rows: Any, on_conflict: str = "") -> _Query:
        self.upserting = rows if isinstance(rows, list) else [rows]
        self.conflict = on_conflict.split(",")
        return self

    def insert(self, row: dict[str, Any]) -> _Query:
        self.store.tables.setdefault(self.table, []).append(row)
        return self

    def execute(self) -> _Resp:
        table = self.store.tables.setdefault(self.table, [])
        if self.upserting is not None:
            for row in self.upserting:
                self.store.writes.append((self.table, copy.deepcopy(row)))
                match = next(
                    (r for r in table if all(r.get(k) == row[k] for k in self.conflict)), None
                )
                if match is None:
                    table.append(dict(row))
                else:
                    match.update(row)
            return _Resp(self.upserting)
        rows = [r for r in table if all(check(r.get(col)) for col, check in self.filters)]
        return _Resp(copy.deepcopy(rows))


class Store:
    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.tables: dict[str, list[dict[str, Any]]] = {
            "platform_config": [
                {"key": ap.SETTINGS_KEY, "value": {"base_per_km_ngwee": 400}},
            ],
            "areas": [
                {"slug": "woodlands", "name": "Woodlands", "zone_key": "lusaka_a", "active": True},
                {"slug": "kabulonga", "name": "Kabulonga", "zone_key": "lusaka_a", "active": True},
                {"slug": "matero", "name": "Matero", "zone_key": "lusaka_b", "active": False},
            ],
            "area_distances": [
                {
                    "from_area": "woodlands",
                    "to_area": "kabulonga",
                    "road_km": 3.15,
                    "minutes": 9,
                    "source": "estimate: great-circle x 1.3 (refresh with OSRM)",
                    "manual_override": False,
                },
                {
                    "from_area": "kabulonga",
                    "to_area": "woodlands",
                    "road_km": "3.15",
                    "minutes": 9,
                    "source": "estimate: great-circle x 1.3 (refresh with OSRM)",
                    "manual_override": False,
                },
            ],
            "audit_log": [],
        }

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def config(self, key: str) -> Any:
        return next(r["value"] for r in self.tables["platform_config"] if r["key"] == key)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    data = Store()
    service = MagicMock()
    service.client = data
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: service)
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    return data


def _as(monkeypatch: pytest.MonkeyPatch, *roles: str) -> None:
    monkeypatch.setattr("app.core.auth._load_user_roles", lambda user_id, client: frozenset(roles))


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Settings + time bands
# ---------------------------------------------------------------------------


def test_admin_reads_effective_settings(
    client: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as(monkeypatch, "admin")
    response = client.get(SETTINGS_URL, headers=TOKEN)
    assert response.status_code == 200, response.text
    assert response.json() == DEFAULT_BODY  # partial row -> defaults fill the rest


def test_admin_updates_settings_as_integers_and_checkout_reads_them_back(
    client: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as(monkeypatch, "admin")
    body = copy.deepcopy(DEFAULT_BODY)
    body.update(base_per_km_ngwee=450, stop_fee_ngwee=1500, intra_area_metres=2500)
    body["time_bands"] = [
        {"key": "evening", "start": "18:30", "end": "20:00", "multiplier_bps": 11500},
        {"key": "morning_peak", "start": "06:30", "end": "09:00", "multiplier_bps": 16000},
    ]
    response = client.put(SETTINGS_URL, headers=TOKEN, json=body)
    assert response.status_code == 200, response.text
    saved = store.config(ap.SETTINGS_KEY)
    assert saved["base_per_km_ngwee"] == 450 and type(saved["base_per_km_ngwee"]) is int
    assert saved["intra_area_km"] == "2.5"  # decimal string, never a float
    assert not any(isinstance(v, float) for v in saved.values())
    bands = store.config(ap.BANDS_KEY)
    assert [b["key"] for b in bands] == ["morning_peak", "evening"]  # stored sorted

    settings = ap.load_settings(store)
    assert settings.base_per_km_ngwee == 450
    assert settings.stop_fee_ngwee == 1500
    assert settings.intra_area_metres == 2500
    assert ap.time_band_for(6 * 60 + 45, settings.time_bands) == ("morning_peak", 16_000)
    assert response.json()["time_bands"][0]["start"] == "06:30"

    audit = store.tables["audit_log"]
    assert len(audit) == 1
    assert audit[0]["action"] == "admin.logistics.area_pricing_settings.update"


@pytest.mark.parametrize(
    ("patch", "status"),
    [
        ({"base_per_km_ngwee": 400.5}, 422),  # float ngwee
        ({"stop_fee_ngwee": "1300"}, 422),  # string ngwee
        ({"min_fee_ngwee": -1}, 422),
        ({"zone_bounds": 1}, 422),
        ({"min_fee_ngwee": 30000, "max_fee_ngwee": 20000}, 422),
        ({"rain_multiplier_bps": 9000}, 422),  # rain never makes delivery cheaper
        ({"quote_ttl_minutes": 0}, 422),
        ({"unknown": 1}, 422),
        (
            {
                "time_bands": [
                    {"key": "a", "start": "07:00", "end": "10:00", "multiplier_bps": 15000},
                    {"key": "bb", "start": "09:00", "end": "11:00", "multiplier_bps": 10000},
                ]
            },
            422,
        ),
        (
            {"time_bands": [{"key": "bb", "start": "10:00", "end": "09:00", "multiplier_bps": 1}]},
            422,
        ),
        (
            {
                "time_bands": [
                    {"key": "bb", "start": "07:00", "end": "08:00", "multiplier_bps": 10000},
                    {"key": "bb", "start": "09:00", "end": "10:00", "multiplier_bps": 10000},
                ]
            },
            422,
        ),
        (
            {
                "time_bands": [
                    {"key": "bb", "start": "7:00", "end": "08:00", "multiplier_bps": 10000}
                ]
            },
            422,
        ),
    ],
)
def test_settings_validation_rejects_and_writes_nothing(
    client: TestClient,
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    patch: dict[str, Any],
    status: int,
) -> None:
    _as(monkeypatch, "admin")
    response = client.put(SETTINGS_URL, headers=TOKEN, json={**DEFAULT_BODY, **patch})
    assert response.status_code == status, response.text
    assert store.writes == []
    assert store.tables["audit_log"] == []


def test_settings_edit_is_full_admin_only(
    client: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Operators with logistics.manage flip rain mode; the price formula stays with admins.
    assert admin_permission_for_request(SETTINGS_URL, "PUT") is None
    assert (
        admin_permission_for_request(
            "/admin/logistics/area-distances/{from_area}/{to_area}", "PATCH"
        )
        is None
    )
    for roles in [("customer",), ("vendor",), ("moderator",)]:
        _as(monkeypatch, *roles)
        assert client.put(SETTINGS_URL, headers=TOKEN, json=DEFAULT_BODY).status_code == 403
        assert client.get(SETTINGS_URL, headers=TOKEN).status_code == 403
    assert client.put(SETTINGS_URL, json=DEFAULT_BODY).status_code == 401
    assert store.writes == []


def test_mutations_are_rate_limited() -> None:
    assert "PUT /logistics/area-pricing/settings" in POLICIES
    assert "PATCH /logistics/area-distances/{from_area}/{to_area}" in POLICIES


# ---------------------------------------------------------------------------
# Distance table
# ---------------------------------------------------------------------------


def test_admin_lists_areas_and_distances(
    client: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as(monkeypatch, "admin")
    areas = client.get("/admin/logistics/areas", headers=TOKEN)
    assert areas.status_code == 200, areas.text
    assert {a["slug"]: a["active"] for a in areas.json()}["matero"] is False
    rows = client.get(
        "/admin/logistics/area-distances", headers=TOKEN, params={"from_area": "woodlands"}
    )
    assert rows.status_code == 200, rows.text
    assert rows.json()["rows"] == [
        {
            "from_area": "woodlands",
            "to_area": "kabulonga",
            "road_km": "3.15",
            "minutes": 9,
            "source": "estimate: great-circle x 1.3 (refresh with OSRM)",
            "manual_override": False,
        }
    ]
    bad = client.get("/admin/logistics/area-distances", headers=TOKEN, params={"from_area": "X;"})
    assert bad.status_code == 422


def test_admin_corrects_a_pair_both_ways_and_marks_it_manual(
    client: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as(monkeypatch, "admin")
    response = client.patch(
        "/admin/logistics/area-distances/woodlands/kabulonga",
        headers=TOKEN,
        json={"road_km": "4.6", "minutes": 14, "both_directions": True},
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert {(r["from_area"], r["to_area"]) for r in out} == {
        ("woodlands", "kabulonga"),
        ("kabulonga", "woodlands"),
    }
    assert all(r["road_km"] == "4.60" and r["manual_override"] for r in out)
    assert all(r["source"] == "manual edit (admin)" for r in out)
    written = [row for table, row in store.writes if table == "area_distances"]
    assert all(row["road_km"] == "4.6" for row in written)  # Decimal string on the wire
    table = ap.load_distances(store, ["woodlands"], ["kabulonga"])
    assert table[("woodlands", "kabulonga")] == ap.Leg(4600, 14)
    audit = store.tables["audit_log"]
    assert len(audit) == 1 and audit[0]["action"] == "admin.logistics.area_distance.update"


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("woodlands/kabulonga", {"road_km": 4.6, "minutes": 14}, 422),  # float km on the wire
        ("woodlands/kabulonga", {"road_km": "4.655", "minutes": 14}, 422),
        ("woodlands/kabulonga", {"road_km": "501", "minutes": 14}, 422),
        ("woodlands/kabulonga", {"road_km": "4.6", "minutes": 601}, 422),
        ("woodlands/woodlands", {"road_km": "1", "minutes": 3}, 422),
        ("woodlands/nowhere", {"road_km": "1", "minutes": 3}, 404),
        ("Woodlands/kabulonga", {"road_km": "1", "minutes": 3}, 422),
    ],
)
def test_distance_edit_validation(
    client: TestClient,
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, Any],
    status: int,
) -> None:
    _as(monkeypatch, "admin")
    response = client.patch(f"/admin/logistics/area-distances/{path}", headers=TOKEN, json=body)
    assert response.status_code == status, response.text
    assert store.writes == []


def test_distance_edit_denied_to_non_admins(
    client: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _as(monkeypatch, "customer")
    response = client.patch(
        "/admin/logistics/area-distances/woodlands/kabulonga",
        headers=TOKEN,
        json={"road_km": "1", "minutes": 3},
    )
    assert response.status_code == 403
    assert store.writes == []


# ---------------------------------------------------------------------------
# Money: integer ngwee, booked to delivery_revenue
# ---------------------------------------------------------------------------


def _line(vendor: str, total: int) -> PricingLine:
    return PricingLine(
        vendor_id=vendor,
        listing_id=f"l-{vendor}",
        qty=1,
        line_total_ngwee=total,
        commission_bps=800,
    )


def test_area_share_is_the_charged_fee_and_is_booked_to_delivery_revenue() -> None:
    settings = ap.AreaPricingSettings()
    quote = ap.quote_address(
        customer_area="kabulonga",
        vendor_areas={"v1": "woodlands", "v2": "woodlands"},
        distances={("woodlands", "kabulonga"): ap.Leg(3150, 9)},
        settings=settings,
        zone_fees={"lusaka_a": 3_000, "lusaka_b": 4_500},
        rain=False,
        promise=ap.DeliveryPromise("today", date(2026, 11, 18), time(12), time(14, 30)),
    )
    assert quote.priced
    shares = quote.fees_by_vendor
    assert all(type(v) is int and v % ap.K5_NGWEE == 0 for v in shares.values())
    assert sum(shares.values()) == quote.total_fee_ngwee

    prices = price_delivery_groups(
        lines=[_line("v1", 50_000), _line("v2", 60_000)],
        delivery_zones={"v1": "lusaka_a", "v2": "lusaka_a"},
        zone_fees={"lusaka_a": 3_000},
        vendor_terms={"v2": VendorDeliveryTerms(free_delivery_all=True)},
        policy=AutoFreeDeliveryPolicy(threshold_ngwee=10**12),
        group_fees=shares,
    )
    # Customer-paid group: the area share (not the zone fee) is the order's delivery fee.
    assert prices["v1"].funding == "customer"
    assert prices["v1"].customer_fee_ngwee == shares["v1"]
    capture = delivery_fee_capture(delivery_fee_ngwee=prices["v1"].customer_fee_ngwee)
    revenue = [leg for leg in capture.legs if leg.account.kind == "delivery_revenue"]
    assert [leg.amount_ngwee for leg in revenue] == [-shares["v1"]]

    # Vendor-funded free delivery: the vendor is charged the area share, still delivery revenue.
    assert prices["v2"].funding == "vendor"
    assert prices["v2"].funded_ngwee == shares["v2"]
    charge = delivery_fee_vendor_charge(funded_ngwee=prices["v2"].funded_ngwee, vendor_id="v2")
    revenue = [leg for leg in charge.legs if leg.account.kind == "delivery_revenue"]
    assert [leg.amount_ngwee for leg in revenue] == [-shares["v2"]]
