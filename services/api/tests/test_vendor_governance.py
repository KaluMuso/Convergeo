"""Vendor cancel-rate governance signal (F11).

Isolation-clean: no network / no DB. Exercises the classifier and the all-vendor
scan against a tiny fake Supabase client, plus the admin endpoint via TestClient
with dependency overrides (auth + client), so no Postgres is needed.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.moderation.vendor_governance import (
    CRITICAL_CANCEL_RATE,
    MIN_ORDERS_FOR_SIGNAL,
    WARN_CANCEL_RATE,
    classify_cancel_rate,
    scan_vendor_governance,
)
from fastapi.testclient import TestClient

ADMIN_ID = "00000000-0000-0000-0000-0000000a0001"

# Deterministic vendor UUIDs (the endpoint coerces vendor_id -> UUID).
V_OK = "11111111-1111-1111-1111-111111111111"
V_WARN = "22222222-2222-2222-2222-222222222222"
V_CRIT = "33333333-3333-3333-3333-333333333333"
V_LOWVOL = "44444444-4444-4444-4444-444444444444"
V_NOORDERS = "55555555-5555-5555-5555-555555555555"
V_INACTIVE = "66666666-6666-6666-6666-666666666666"


# --------------------------------------------------------------------------- #
# Fake Supabase client (vendors + orders only)
# --------------------------------------------------------------------------- #
class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append((column, value))
        return self

    def execute(self) -> _FakeResult:
        rows = [
            row
            for row in self._rows
            if all(row.get(col) == val for col, val in self._filters)
        ]
        return _FakeResult(rows)


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return _FakeQuery(self.rows).select(*args, **kwargs)


class _FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {"vendors": _FakeTable(), "orders": _FakeTable()}

    def table(self, name: str) -> _FakeTable:
        if name not in self.tables:
            self.tables[name] = _FakeTable()
        return self.tables[name]


class _FakeWrapper:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client


def _vendor(vendor_id: str, name: str, status: str = "active") -> dict[str, Any]:
    return {"id": vendor_id, "display_name": name, "slug": name.lower(), "status": status}


def _orders(vendor_id: str, *, total: int, cancelled: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(total):
        status = "cancelled" if i < cancelled else "completed"
        rows.append({"vendor_id": vendor_id, "status": status})
    return rows


def _seed(client: _FakeClient) -> None:
    client.tables["vendors"].rows.extend(
        [
            _vendor(V_OK, "OkShop"),
            _vendor(V_WARN, "WarnShop"),
            _vendor(V_CRIT, "CritShop"),
            _vendor(V_LOWVOL, "LowVol"),
            _vendor(V_NOORDERS, "Fresh"),
            _vendor(V_INACTIVE, "Gone", status="suspended"),
        ]
    )
    orders = client.tables["orders"].rows
    orders.extend(_orders(V_OK, total=20, cancelled=0))  # 0%   -> ok
    orders.extend(_orders(V_WARN, total=20, cancelled=1))  # 5%   -> warn
    orders.extend(_orders(V_CRIT, total=20, cancelled=4))  # 20%  -> critical
    orders.extend(_orders(V_LOWVOL, total=4, cancelled=3))  # 75% but < min -> ok
    orders.extend(_orders(V_INACTIVE, total=20, cancelled=20))  # excluded (not active)


# --------------------------------------------------------------------------- #
# classify_cancel_rate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("rate", "total", "expected"),
    [
        (0.04, 100, "ok"),  # below warn
        (WARN_CANCEL_RATE, 100, "warn"),  # exactly at warn
        (0.07, 100, "warn"),  # between warn and critical
        (CRITICAL_CANCEL_RATE, 100, "critical"),  # exactly at critical
        (0.5, 100, "critical"),  # well above critical
        (0.5, MIN_ORDERS_FOR_SIGNAL - 1, "ok"),  # high rate but below min orders
        (WARN_CANCEL_RATE, MIN_ORDERS_FOR_SIGNAL, "warn"),  # min-orders boundary counts
        (0.0, 0, "ok"),  # no orders
    ],
)
def test_classify_cancel_rate(rate: float, total: int, expected: str) -> None:
    assert classify_cancel_rate(rate, total) == expected


def test_thresholds_single_sourced_with_badge() -> None:
    from app.services.kyc.badge import MAX_CANCEL_RATE

    # The warn line must equal the D9 preferred-badge cancel gate.
    assert WARN_CANCEL_RATE == MAX_CANCEL_RATE
    assert CRITICAL_CANCEL_RATE > WARN_CANCEL_RATE


# --------------------------------------------------------------------------- #
# scan_vendor_governance
# --------------------------------------------------------------------------- #
def _scan(min_severity: Any) -> list[Any]:
    client = _FakeClient()
    _seed(client)
    return scan_vendor_governance(_FakeWrapper(client), min_severity=min_severity)


def test_scan_warn_returns_warn_and_critical_sorted() -> None:
    signals = _scan("warn")
    ids = [s.vendor_id for s in signals]
    # critical first (higher severity), then warn; ok/low-vol/inactive excluded.
    assert ids == [V_CRIT, V_WARN]
    assert signals[0].severity == "critical"
    assert signals[0].cancelled_orders == 4
    assert signals[0].total_orders == 20
    assert signals[0].cancel_rate == pytest.approx(0.2)
    assert signals[1].severity == "warn"
    assert signals[1].cancel_rate == pytest.approx(0.05)


def test_scan_critical_only() -> None:
    signals = _scan("critical")
    assert [s.vendor_id for s in signals] == [V_CRIT]


def test_scan_all_includes_ok_active_but_not_inactive() -> None:
    signals = _scan("ok")
    ids = {s.vendor_id for s in signals}
    # Every active vendor appears; the suspended one never does.
    assert ids == {V_OK, V_WARN, V_CRIT, V_LOWVOL, V_NOORDERS}
    assert V_INACTIVE not in ids
    by_id = {s.vendor_id: s for s in signals}
    assert by_id[V_OK].severity == "ok"
    assert by_id[V_LOWVOL].severity == "ok"  # 75% but only 4 orders
    assert by_id[V_LOWVOL].cancel_rate == pytest.approx(0.75)
    assert by_id[V_NOORDERS].total_orders == 0
    assert by_id[V_NOORDERS].severity == "ok"


def test_scan_sort_orders_by_rate_within_severity() -> None:
    client = _FakeClient()
    client.tables["vendors"].rows.extend(
        [_vendor(V_WARN, "WarnA"), _vendor(V_CRIT, "WarnB")]
    )
    # Both "warn" tier; V_CRIT id here carries the higher rate (9% > 6%).
    client.tables["orders"].rows.extend(_orders(V_WARN, total=100, cancelled=6))
    client.tables["orders"].rows.extend(_orders(V_CRIT, total=100, cancelled=9))
    signals = scan_vendor_governance(_FakeWrapper(client), min_severity="warn")
    assert [s.vendor_id for s in signals] == [V_CRIT, V_WARN]  # higher rate first


# --------------------------------------------------------------------------- #
# Admin endpoint
# --------------------------------------------------------------------------- #
@pytest.fixture
def admin_client() -> Generator[TestClient, None, None]:
    app = create_app()
    client = _FakeClient()
    _seed(client)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=ADMIN_ID, roles=frozenset({"admin"}), token="test-token"
    )
    app.dependency_overrides[get_supabase_client] = lambda: _FakeWrapper(client)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_endpoint_default_warn_lists_offenders(admin_client: TestClient) -> None:
    response = admin_client.get("/admin/governance/vendors")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["severity_filter"] == "warn"
    assert body["warn_threshold"] == WARN_CANCEL_RATE
    assert body["critical_threshold"] == CRITICAL_CANCEL_RATE
    assert body["min_orders"] == MIN_ORDERS_FOR_SIGNAL
    severities = [v["severity"] for v in body["vendors"]]
    assert severities == ["critical", "warn"]
    assert body["vendors"][0]["vendor_id"] == V_CRIT
    assert body["vendors"][0]["cancelled_orders"] == 4


def test_endpoint_critical_filter(admin_client: TestClient) -> None:
    response = admin_client.get("/admin/governance/vendors", params={"severity": "critical"})
    assert response.status_code == 200, response.text
    vendors = response.json()["vendors"]
    assert [v["vendor_id"] for v in vendors] == [V_CRIT]


def test_endpoint_all_includes_healthy_vendors(admin_client: TestClient) -> None:
    response = admin_client.get("/admin/governance/vendors", params={"severity": "all"})
    assert response.status_code == 200, response.text
    ids = {v["vendor_id"] for v in response.json()["vendors"]}
    assert ids == {V_OK, V_WARN, V_CRIT, V_LOWVOL, V_NOORDERS}


def test_endpoint_rejects_non_admin() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-0000000e0001", roles=frozenset({"vendor"}), token="t"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/admin/governance/vendors")
    app.dependency_overrides.clear()
    assert response.status_code == 403
