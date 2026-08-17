from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.errors import AppError
from app.services.fx.rates import (
    build_order_fx_snapshot,
    load_current_usd_zmw_rate,
    publish_usd_zmw_rate,
    require_fresh_usd_zmw_rate,
)


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeFxClient:
    def __init__(self) -> None:
        self.fx_rates: list[dict[str, Any]] = []
        self.platform_config: list[dict[str, Any]] = [
            {"key": "fx_rate_max_age_hours", "value": 24}
        ]

    def table(self, name: str) -> "_Query":
        return _Query(self, name)


class _Query:
    def __init__(self, store: FakeFxClient, name: str) -> None:
        self._store = store
        self._name = name
        self._filters: list[tuple[str, Any]] = []
        self._null_cols: list[str] = []
        self._update: dict[str, Any] | None = None
        self._insert: dict[str, Any] | None = None
        self._limit: int | None = None

    def select(self, _columns: str) -> _Query:
        return self

    def eq(self, key: str, value: Any) -> _Query:
        self._filters.append((key, value))
        return self

    def is_(self, key: str, value: Any) -> _Query:
        if value is None:
            self._null_cols.append(key)
        return self

    def limit(self, value: int) -> _Query:
        self._limit = value
        return self

    def order(self, _key: str, *, desc: bool = False) -> _Query:
        _ = desc
        return self

    def maybe_single(self) -> _Query:
        self._limit = 1
        return self

    def update(self, payload: dict[str, Any]) -> _Query:
        self._update = payload
        return self

    def insert(self, payload: dict[str, Any]) -> _Query:
        self._insert = payload
        return self

    def execute(self) -> _Result:
        if self._name == "platform_config":
            rows = list(self._store.platform_config)
            for key, value in self._filters:
                rows = [row for row in rows if row.get(key) == value]
            if self._limit == 1:
                return _Result(rows[0] if rows else None)
            return _Result(rows)
        if self._insert is not None:
            self._store.fx_rates.append(dict(self._insert))
            return _Result([self._insert])
        rows = list(self._store.fx_rates)
        for col in self._null_cols:
            rows = [row for row in rows if row.get(col) is None]
        for key, value in self._filters:
            rows = [row for row in rows if row.get(key) == value]
        if self._update is not None:
            for row in rows:
                row.update(self._update)
            return _Result(rows)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


def _fresh_window() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - timedelta(minutes=5), now + timedelta(hours=12)


def test_require_fresh_rate_blocks_when_unpublished() -> None:
    client = FakeFxClient()
    with pytest.raises(AppError) as exc_info:
        require_fresh_usd_zmw_rate(client)
    assert exc_info.value.code == "fx.rate_unavailable"


def test_require_fresh_rate_blocks_when_expired() -> None:
    client = FakeFxClient()
    now = datetime.now(UTC)
    client.fx_rates.append(
        {
            "id": "rate-stale",
            "base_currency": "USD",
            "quote_currency": "ZMW",
            "rate_zmw_per_usd_micros": 27_000_000_000,
            "vendor_margin_bps": 0,
            "source": "BOZ",
            "source_reference": None,
            "effective_at": (now - timedelta(days=2)).isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
            "superseded_at": None,
        }
    )
    with pytest.raises(AppError) as exc_info:
        require_fresh_usd_zmw_rate(client, now=now)
    assert exc_info.value.code == "fx.rate_stale"


def test_publish_and_load_current_rate() -> None:
    client = FakeFxClient()
    effective_at, expires_at = _fresh_window()
    snapshot = publish_usd_zmw_rate(
        client,
        rate_zmw_per_usd_micros=27_500_000_000,
        vendor_margin_bps=150,
        source="Bank of Zambia",
        source_reference="daily",
        effective_at=effective_at,
        expires_at=expires_at,
        created_by="11111111-1111-1111-1111-111111111111",
    )
    loaded = load_current_usd_zmw_rate(client)
    assert loaded is not None
    assert loaded.rate_id == snapshot.rate_id
    assert loaded.vendor_margin_bps == 150
    assert not loaded.stale


def test_zmw_only_order_snapshot_does_not_convert() -> None:
    payload = build_order_fx_snapshot(used_usd=False, rate=None)
    assert payload == {"quote_currency": "ZMW", "conversion_applied": False}


def test_usd_order_snapshot_requires_rate() -> None:
    with pytest.raises(AppError) as exc_info:
        build_order_fx_snapshot(used_usd=True, rate=None)
    assert exc_info.value.code == "fx.rate_unavailable"


def test_public_fx_rate_endpoint_unpublished(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.deps import get_supabase_client
    from app.main import create_app
    from fastapi.testclient import TestClient

    class Wrapper:
        client = FakeFxClient()

    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: Wrapper()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/public/config/fx-rate")
    assert response.status_code == 200
    body = response.json()
    assert body["published"] is False
    assert body["stale"] is True
