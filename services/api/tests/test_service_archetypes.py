"""Service archetypes: derivation, per-archetype attribute validation, API wiring.

Design: docs/plan/service-type-templates.md. Defended claims:

* a vertical derives an archetype, a stored override wins, unknown falls back to
  ``professional``;
* offer and service attributes are validated per archetype (unknown keys, out-of-range
  numbers, non-integer money and bad shapes are refused with ``invalid_attributes``);
* reads are tolerant: a stored blob that no longer validates degrades to ``{}``;
* package writes validate against the service's EFFECTIVE archetype and screen text;
* the browse list carries archetype/rating/availability and filters by price band,
  rating and availability.
"""

# ruff: noqa: F811
from __future__ import annotations

from typing import Any

import pytest
from app.errors import AppError
from app.routers.services_listings import SERVICE_VERTICALS, build_browse_response
from app.schemas.service_archetypes import (
    ARCHETYPES,
    VERTICAL_ARCHETYPE,
    derive_archetype,
    effective_archetype,
    tolerant_offer_attributes,
    tolerant_service_attributes,
    validate_offer_attributes,
    validate_service_attributes,
)
from fastapi.testclient import TestClient

# Reuse the fake database and fixtures from the packages tests.
from test_service_packages import (  # noqa: F401  (pytest fixtures)
    SERVICE_ID,
    FakeClient,
    _pkg,
    customer,
    db,
    vendor,
)


# --- derivation ---------------------------------------------------------------
def test_every_vertical_maps_to_a_known_archetype() -> None:
    assert set(SERVICE_VERTICALS) == set(VERTICAL_ARCHETYPE)
    assert set(VERTICAL_ARCHETYPE.values()) <= set(ARCHETYPES)
    assert len(ARCHETYPES) == 7


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("lodging", "accommodation"),
        ("property", "accommodation"),
        ("beauty", "appointment"),
        ("fitness", "membership"),
        ("cleaning", "on_site"),
        ("rentals", "rental"),
        ("family-fun", "ticketed"),
        ("staffing", "professional"),
        ("something-new", "professional"),
        (None, "professional"),
    ],
)
def test_derive_archetype(category: str | None, expected: str) -> None:
    assert derive_archetype(category) == expected


def test_stored_override_wins_and_garbage_override_is_ignored() -> None:
    assert effective_archetype({"category": "beauty", "archetype": "rental"}) == "rental"
    assert effective_archetype({"category": "beauty", "archetype": None}) == "appointment"
    assert effective_archetype({"category": "beauty", "archetype": "nonsense"}) == "appointment"


# --- offer attributes ----------------------------------------------------------
def test_accommodation_offer_accepts_a_room() -> None:
    out = validate_offer_attributes(
        "accommodation",
        {"room_type": "presidential", "sleeps": 4, "beds": 2, "bed_type": "king", "min_nights": 2},
    )
    assert out["room_type"] == "presidential" and out["sleeps"] == 4


@pytest.mark.parametrize(
    ("archetype", "bad"),
    [
        ("accommodation", {"sleeps": 0}),
        ("accommodation", {"room_type": "castle"}),
        ("accommodation", {"unknown_key": 1}),
        ("appointment", {"duration_min": 7}),
        ("appointment", {"duration_min": 600}),
        ("membership", {"pass_kind": "forever"}),
        ("membership", {"guest_passes": 11}),
        ("on_site", {"crew_size": 0}),
        ("rental", {"deposit_ngwee": 12.5}),
        ("rental", {"deposit_ngwee": "5000"}),
        ("rental", {"deposit_ngwee": 0}),
        ("rental", {"specs": [{"label": "a", "value": "b"}] * 9}),
        ("ticketed", {"age_min": 10, "age_max": 5}),
        ("ticketed", {"party_size": 21}),
        ("professional", {"experience_years": 51}),
        ("professional", {"certifications": ["a"] * 6}),
        ("accommodation", {"image": "https://evil.example/x.png"}),
    ],
)
def test_offer_validation_refuses_bad_values(archetype: str, bad: dict[str, Any]) -> None:
    with pytest.raises(AppError) as exc:
        validate_offer_attributes(archetype, bad)
    assert exc.value.code == "invalid_attributes" and exc.value.http_status == 422


def test_rental_deposit_is_integer_ngwee() -> None:
    out = validate_offer_attributes("rental", {"unit": "day", "deposit_ngwee": 50_000})
    assert out["deposit_ngwee"] == 50_000 and isinstance(out["deposit_ngwee"], int)


def test_attributes_must_be_an_object_and_bounded() -> None:
    with pytest.raises(AppError):
        validate_offer_attributes("rental", ["x"])
    with pytest.raises(AppError):
        validate_offer_attributes("professional", {"role": "x" * 41})


def test_offer_shape_depends_on_archetype() -> None:
    # A salon duration is not a valid hotel attribute.
    validate_offer_attributes("appointment", {"duration_min": 45})
    with pytest.raises(AppError):
        validate_offer_attributes("accommodation", {"duration_min": 45})


def test_tolerant_read_degrades_to_empty() -> None:
    assert tolerant_offer_attributes("rental", {"deposit_ngwee": 1.5}) == {}
    assert tolerant_service_attributes("membership", {"class_schedule": "nope"}) == {}
    assert tolerant_offer_attributes("rental", None) == {}


# --- service attributes ---------------------------------------------------------
def test_membership_service_schedule() -> None:
    out = validate_service_attributes(
        "membership",
        {
            "availability": "limited",
            "class_schedule": [
                {"day": 1, "start": "06:30", "title": "Spin", "duration_min": 45, "capacity": 20}
            ],
        },
    )
    assert out["class_schedule"][0]["title"] == "Spin"


@pytest.mark.parametrize(
    ("archetype", "bad"),
    [
        ("membership", {"class_schedule": [{"day": 7, "start": "06:30", "title": "x"}]}),
        ("membership", {"class_schedule": [{"day": 1, "start": "25:00", "title": "x"}]}),
        ("membership", {"class_schedule": [{"day": 1, "start": "06:30", "title": "x"}] * 22}),
        ("accommodation", {"check_in": "2pm"}),
        ("appointment", {"staff": [{"name": "A"}] * 11}),
        ("professional", {"availability": "maybe"}),
        ("rental", {"policy": {"cancellation": "whenever"}}),
    ],
)
def test_service_validation_refuses_bad_values(archetype: str, bad: dict[str, Any]) -> None:
    with pytest.raises(AppError):
        validate_service_attributes(archetype, bad)


# --- package API ------------------------------------------------------------------
def test_package_attributes_validated_against_service_archetype(
    vendor: TestClient, db: FakeClient
) -> None:
    # printing-creative derives `professional`: room attributes are refused.
    bad = vendor.post(
        f"/vendor/services/{SERVICE_ID}/packages", json=_pkg(attributes={"sleeps": 2})
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_attributes"
    assert db.rows("service_packages") == []

    ok = vendor.post(
        f"/vendor/services/{SERVICE_ID}/packages",
        json=_pkg(attributes={"rate_unit": "project", "experience_years": 5}),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["attributes"] == {"rate_unit": "project", "experience_years": 5}


def test_override_changes_which_attributes_are_valid(vendor: TestClient, db: FakeClient) -> None:
    service = next(r for r in db.rows("services") if r["id"] == SERVICE_ID)
    service["archetype"] = "rental"
    res = vendor.post(
        f"/vendor/services/{SERVICE_ID}/packages",
        json=_pkg(attributes={"unit": "day", "deposit_ngwee": 20_000, "quantity_available": 3}),
    )
    assert res.status_code == 200, res.text
    assert res.json()["attributes"]["deposit_ngwee"] == 20_000


def test_package_attribute_text_is_screened(vendor: TestClient, db: FakeClient) -> None:
    from app.services.moderation import prohibited

    sample = _first_prohibited(prohibited)
    if sample is None:
        pytest.skip("no prohibited keyword available to probe the screen")
    res = vendor.post(
        f"/vendor/services/{SERVICE_ID}/packages",
        json=_pkg(attributes={"role": sample[:40]}),
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "prohibited_listing"


def _first_prohibited(module: Any) -> str | None:
    for name in dir(module):
        value = getattr(module, name)
        if name.isupper() and isinstance(value, (tuple, list, frozenset, set)) and value:
            for item in value:
                if isinstance(item, str) and 3 <= len(item) <= 30:
                    verdict = module.screen_listing(title=item, description=None, category=None)
                    if not verdict.allowed:
                        return item
    return None


def test_public_detail_exposes_archetype_and_tolerant_attributes(
    customer: TestClient, db: FakeClient
) -> None:
    service = next(r for r in db.rows("services") if r["id"] == SERVICE_ID)
    service["category"] = "lodging"
    service["attributes"] = {"check_in": "14:00", "availability": "limited"}
    db.rows("service_packages").extend(
        [
            {
                "id": "p1",
                "service_id": SERVICE_ID,
                "vendor_id": service["vendor_id"],
                "name": "Standard room",
                "price_ngwee": 80_000,
                "delivery_days": 1,
                "includes": [],
                "attributes": {"sleeps": 2, "room_type": "standard"},
                "sort_order": 0,
                "status": "active",
            },
            {
                "id": "p2",
                "service_id": SERVICE_ID,
                "vendor_id": service["vendor_id"],
                "name": "Broken",
                "price_ngwee": 90_000,
                "delivery_days": 1,
                "includes": [],
                "attributes": {"sleeps": 999},
                "sort_order": 1,
                "status": "active",
            },
        ]
    )
    res = customer.get(f"/services/{SERVICE_ID}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["archetype"] == "accommodation"
    assert body["attributes"]["check_in"] == "14:00"
    by_name = {p["name"]: p for p in body["packages"]}
    assert by_name["Standard room"]["attributes"]["sleeps"] == 2
    assert by_name["Broken"]["attributes"] == {}  # degraded, page still renders


def test_snapshot_carries_attributes() -> None:
    from app.services.service_packages import state

    snap = state.snapshot({"id": "x", "name": "n", "attributes": {"sleeps": 2}})
    assert snap["attributes"] == {"sleeps": 2}
    assert state.snapshot({"id": "x", "name": "n"})["attributes"] == {}


# --- browse filters -----------------------------------------------------------------
class _Q:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, *_a: Any, **_k: Any) -> _Q:
        return self

    def eq(self, column: str, value: Any) -> _Q:
        if "." not in column:
            self.rows = [r for r in self.rows if r.get(column) == value]
        return self

    def in_(self, column: str, values: list[Any]) -> _Q:
        self.rows = [r for r in self.rows if r.get(column) in values]
        return self

    def ilike(self, column: str, pattern: str) -> _Q:
        needle = pattern.strip("%").lower()
        self.rows = [r for r in self.rows if needle in str(r.get(column) or "").lower()]
        return self

    def gte(self, column: str, value: int) -> _Q:
        self.rows = [r for r in self.rows if r.get(column) is not None and r[column] >= value]
        return self

    def lte(self, column: str, value: int) -> _Q:
        self.rows = [r for r in self.rows if r.get(column) is not None and r[column] <= value]
        return self

    def order(self, *_a: Any, **_k: Any) -> _Q:
        return self

    def execute(self) -> Any:
        from unittest.mock import MagicMock

        return MagicMock(data=[dict(r) for r in self.rows])


class _Db:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> _Q:
        return _Q(list(self.tables.get(name, [])))


def _svc(sid: str, vendor: str, category: str, price: int | None, **extra: Any) -> dict[str, Any]:
    return {
        "id": sid,
        "vendor_id": vendor,
        "category": category,
        "title": sid,
        "service_area": "Lusaka",
        "from_price_ngwee": price,
        "is_free": False,
        "portfolio_images": [],
        "status": "active",
        "vendors": {"id": vendor, "slug": vendor, "display_name": vendor, "status": "active"},
        **extra,
    }


@pytest.fixture
def browse_db() -> _Db:
    return _Db(
        {
            "services": [
                _svc("room", "v1", "lodging", 80_000),
                _svc("cut", "v2", "beauty", 15_000, attributes={"availability": "unavailable"}),
                _svc("gym", "v3", "fitness", 30_000, archetype="membership"),
                _svc("quote", "v3", "staffing", None),
            ],
            "vendors": [],
            "job_quotes": [],
            "jobs": [],
            "service_reviews": [
                {"provider_vendor_id": "v1", "rating": 5, "status": "published"},
                {"provider_vendor_id": "v1", "rating": 4, "status": "published"},
                {"provider_vendor_id": "v2", "rating": 3, "status": "published"},
            ],
        }
    )


def _ids(resp: Any) -> list[str]:
    return sorted(i.id for i in resp.items)


def test_browse_items_carry_archetype_rating_and_availability(browse_db: _Db) -> None:
    resp = build_browse_response(browse_db)
    by_id = {i.id: i for i in resp.items}
    assert by_id["room"].archetype == "accommodation"
    assert by_id["room"].rating_avg == 4.5 and by_id["room"].rating_count == 2
    assert by_id["gym"].rating_avg is None
    assert by_id["cut"].availability == "unavailable"
    assert by_id["quote"].archetype == "professional"


def test_browse_price_band_uses_integer_ngwee_and_drops_quote_only(browse_db: _Db) -> None:
    mid = build_browse_response(browse_db, price_min=10_000, price_max=50_000)
    assert _ids(mid) == ["cut", "gym"]
    assert "quote" not in _ids(build_browse_response(browse_db, price_min=1))


def test_browse_rating_and_availability_filters(browse_db: _Db) -> None:
    assert _ids(build_browse_response(browse_db, min_rating=4)) == ["room"]
    assert _ids(build_browse_response(browse_db, min_rating=3)) == ["cut", "room"]
    avail = build_browse_response(browse_db, available_only=True)
    assert "cut" not in _ids(avail)


def test_browse_rating_read_failure_degrades_to_no_ratings(browse_db: _Db) -> None:
    class Boom(_Db):
        def table(self, name: str) -> _Q:
            if name == "service_reviews":
                raise RuntimeError("down")
            return super().table(name)

    resp = build_browse_response(Boom(browse_db.tables))
    assert len(resp.items) == 4 and all(i.rating_avg is None for i in resp.items)
