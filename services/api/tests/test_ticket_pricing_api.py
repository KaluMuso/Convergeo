"""DB-free tests for the M10-P15 organiser ticket-pricing write API.

Exercises the full HTTP -> handler -> authz -> validation flow against an
in-memory fake Supabase client (no Postgres; runs under the plain Python CI job).
The money discipline under test: discounts are only ever *below* the base price,
pricing is rejected on free ticket types, early-bird is both-or-neither with a
future cutoff, and the tier PUT replaces the full set (upsert desired + delete
the rest).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EVENT_A_ID = "e1000000-0000-0000-0000-000000000001"
PAID_TYPE_ID = "t1000000-0000-0000-0000-000000000001"
FREE_TYPE_ID = "t1000000-0000-0000-0000-000000000002"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"
BASE_PRICE = 50_000


class _FakeQuery:
    def __init__(self, parent: _FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: Any = None
        self._order: tuple[str, bool] | None = None
        self._on_conflict: list[str] = []

    def select(self, columns: str, *, count: str | None = None) -> _FakeQuery:
        _ = (columns, count)
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _FakeQuery:
        self._filters.append(("in", column, list(values)))
        return self

    def order(self, column: str, *, desc: bool = False) -> _FakeQuery:
        self._order = (column, desc)
        return self

    def maybe_single(self) -> _FakeQuery:
        self._maybe_single = True
        return self

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def upsert(self, payload: Any, *, on_conflict: str) -> _FakeQuery:
        self._pending_op = "upsert"
        self._payload = payload
        self._on_conflict = [col.strip() for col in on_conflict.split(",")]
        return self

    def delete(self) -> _FakeQuery:
        self._pending_op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            if self._maybe_single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        if self._pending_op == "upsert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            written: list[dict[str, Any]] = []
            for row in rows:
                match = next(
                    (
                        e
                        for e in self._parent.rows
                        if all(e.get(k) == row.get(k) for k in self._on_conflict)
                    ),
                    None,
                )
                if match is not None:
                    match.update(row)
                    written.append(dict(match))
                else:
                    stored = dict(row)
                    self._parent.rows.append(stored)
                    written.append(dict(stored))
            return MagicMock(data=written, count=len(written))

        if self._pending_op == "delete":
            kept: list[dict[str, Any]] = []
            deleted = 0
            for row in self._parent.rows:
                if self._matches(row):
                    deleted += 1
                else:
                    kept.append(row)
            self._parent.rows[:] = kept
            return MagicMock(data=[], count=deleted)

        rows = [row for row in self._parent.rows if self._matches(row)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda r: r.get(column, 0), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in value:
                return False
        return True


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> _FakeQuery:
        return _FakeQuery(self, []).select(columns, count=count)

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self, []).update(payload)

    def upsert(self, payload: Any, *, on_conflict: str) -> _FakeQuery:
        return _FakeQuery(self, []).upsert(payload, on_conflict=on_conflict)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self, []).delete()


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {
            "vendors": _FakeTable(),
            "events": _FakeTable(),
            "ticket_types": _FakeTable(),
            "ticket_type_price_tiers": _FakeTable(),
        }

    def table(self, name: str) -> _FakeTable:
        return self.tables.setdefault(name, _FakeTable())


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _past_iso(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _seed(fake: _FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {"id": VENDOR_A_ID, "owner_user_id": USER_A_ID, "status": "active", "kyc_tier": 2},
            {"id": VENDOR_B_ID, "owner_user_id": USER_B_ID, "status": "active", "kyc_tier": 2},
        ]
    )
    fake.tables["events"].rows.append(
        {"id": EVENT_A_ID, "organiser_vendor_id": VENDOR_A_ID, "status": "published"}
    )
    fake.tables["ticket_types"].rows.extend(
        [
            {
                "id": PAID_TYPE_ID,
                "event_id": EVENT_A_ID,
                "kind": "fixed",
                "name": "GA",
                "price_ngwee": BASE_PRICE,
                "qty_cap": None,
                "per_customer_cap": None,
                "early_bird_price_ngwee": None,
                "early_bird_until": None,
            },
            {
                "id": FREE_TYPE_ID,
                "event_id": EVENT_A_ID,
                "kind": "free_rsvp",
                "name": "RSVP",
                "price_ngwee": 0,
                "qty_cap": None,
                "per_customer_cap": None,
                "early_bird_price_ngwee": None,
                "early_bird_until": None,
            },
        ]
    )


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(token: str, settings: Any) -> dict[str, Any]:
        _ = settings
        if token == TOKEN_A:
            return {"sub": USER_A_ID, "exp": 9_999_999_999}
        if token == TOKEN_B:
            return {"sub": USER_B_ID, "exp": 9_999_999_999}
        raise ValueError("invalid token")

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


@pytest.fixture
def fake() -> _FakeSupabaseClient:
    client = _FakeSupabaseClient()
    _seed(client)
    return client


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    fake: _FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch)
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _tiers(fake: _FakeSupabaseClient) -> list[tuple[int, int]]:
    return sorted(
        (int(r["min_qty"]), int(r["price_ngwee"]))
        for r in fake.tables["ticket_type_price_tiers"].rows
    )


def _tier(min_qty: int, price_ngwee: int) -> dict[str, int]:
    return {"min_qty": min_qty, "price_ngwee": price_ngwee}


# --- reads -----------------------------------------------------------------


def test_get_pricing_empty(client: TestClient) -> None:
    resp = client.get(f"/organiser/ticket-types/{PAID_TYPE_ID}/pricing", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_price_ngwee"] == BASE_PRICE
    assert body["early_bird_price_ngwee"] is None
    assert body["early_bird_until"] is None
    assert body["tiers"] == []


# --- early-bird ------------------------------------------------------------


def test_set_early_bird_configures_and_persists(
    client: TestClient, fake: _FakeSupabaseClient
) -> None:
    cutoff = _future_iso()
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": 40_000, "early_bird_until": cutoff},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["early_bird_price_ngwee"] == 40_000
    assert body["early_bird_until"] == cutoff
    stored = fake.tables["ticket_types"].rows[0]
    assert stored["early_bird_price_ngwee"] == 40_000
    assert stored["early_bird_until"] == cutoff


def test_clear_early_bird(client: TestClient, fake: _FakeSupabaseClient) -> None:
    fake.tables["ticket_types"].rows[0]["early_bird_price_ngwee"] = 40_000
    fake.tables["ticket_types"].rows[0]["early_bird_until"] = _future_iso()
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": None, "early_bird_until": None},
    )
    assert resp.status_code == 200
    assert resp.json()["early_bird_price_ngwee"] is None
    assert fake.tables["ticket_types"].rows[0]["early_bird_price_ngwee"] is None
    assert fake.tables["ticket_types"].rows[0]["early_bird_until"] is None


def test_early_bird_rejects_non_discount(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": BASE_PRICE, "early_bird_until": _future_iso()},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "early_bird_not_a_discount"


def test_early_bird_rejects_past_cutoff(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": 40_000, "early_bird_until": _past_iso()},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "early_bird_cutoff_in_past"


def test_early_bird_rejects_free_type(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{FREE_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": 0, "early_bird_until": _future_iso()},
    )
    # price 0 >= base 0 is caught first as "not allowed on free" (base <= 0).
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "pricing_not_allowed_on_free"


def test_early_bird_both_or_neither(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": 40_000},
    )
    assert resp.status_code == 422  # Pydantic model-validator


def test_early_bird_rejects_float_price(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/early-bird",
        headers=_headers(),
        json={"early_bird_price_ngwee": 40_000.5, "early_bird_until": _future_iso()},
    )
    assert resp.status_code == 422  # NgweeInt forbids float money


# --- group tiers -----------------------------------------------------------


def test_set_price_tiers_configures_and_persists(
    client: TestClient, fake: _FakeSupabaseClient
) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, 45_000), _tier(10, 40_000)]},
    )
    assert resp.status_code == 200
    assert resp.json()["tiers"] == [
        {"min_qty": 5, "price_ngwee": 45_000},
        {"min_qty": 10, "price_ngwee": 40_000},
    ]
    assert _tiers(fake) == [(5, 45_000), (10, 40_000)]


def test_price_tiers_replace_semantics(client: TestClient, fake: _FakeSupabaseClient) -> None:
    client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, 45_000), _tier(10, 40_000)]},
    )
    # New desired set drops min_qty=10, keeps/updates 5, adds 8.
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, 46_000), _tier(8, 42_000)]},
    )
    assert resp.status_code == 200
    assert _tiers(fake) == [(5, 46_000), (8, 42_000)]


def test_empty_tiers_clears_all(client: TestClient, fake: _FakeSupabaseClient) -> None:
    client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, 45_000)]},
    )
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": []},
    )
    assert resp.status_code == 200
    assert _tiers(fake) == []


def test_price_tiers_reject_non_discount(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, BASE_PRICE)]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "tier_not_a_discount"


def test_price_tiers_reject_free_type(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{FREE_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, 1_000)]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "pricing_not_allowed_on_free"


def test_price_tiers_reject_min_qty_one(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(1, 45_000)]},
    )
    assert resp.status_code == 422  # Field(ge=2)


def test_price_tiers_reject_duplicate_min_qty(client: TestClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(),
        json={"tiers": [_tier(5, 45_000), _tier(5, 44_000)]},
    )
    assert resp.status_code == 422  # model-validator: duplicate min_qty


# --- authz -----------------------------------------------------------------


def test_cross_owner_forbidden(client: TestClient, fake: _FakeSupabaseClient) -> None:
    resp = client.put(
        f"/organiser/ticket-types/{PAID_TYPE_ID}/price-tiers",
        headers=_headers(TOKEN_B),  # vendor B does not own event A
        json={"tiers": [_tier(5, 45_000)]},
    )
    assert resp.status_code == 403
    assert _tiers(fake) == []


def test_anonymous_denied(client: TestClient) -> None:
    resp = client.get(f"/organiser/ticket-types/{PAID_TYPE_ID}/pricing")
    assert resp.status_code == 401
