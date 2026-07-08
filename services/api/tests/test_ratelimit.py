from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.ratelimit import (
    RateLimitConfig,
    bump_rate_counter,
    check_active_cooldown,
    check_and_increment_otp_quota,
    clear_rate_limit_config_cache,
    compute_resend_cooldown_seconds,
    load_rate_limit_config,
    raise_rate_limited,
)
from app.errors import AppError
from app.main import create_app
from fastapi.testclient import TestClient


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def gt(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gt", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._pending_op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            self._parent.rows.append(dict(self._payload))
            return MagicMock(data=[self._payload])

        if self._pending_op == "delete":
            self._parent.rows = self._apply_filters(self._parent.rows)
            deleted = len(self._parent.rows)
            self._parent.rows = []
            return MagicMock(data=[], count=deleted)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row[column], reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "gt":
                filtered = [
                    row
                    for row in filtered
                    if str(row.get(column, "")) > str(value)
                ]
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, []).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self, []).delete()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "platform_config": FakeTable(),
            "rate_counters": FakeTable(),
        }
        self.rpc_results: dict[str, list[dict[str, Any]]] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, name: str) -> FakeTable:
        return self.tables[name]

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.rpc_calls.append((name, params))

        class RpcQuery:
            def __init__(self, outer: FakeSupabaseClient, fn: str, payload: dict[str, Any]) -> None:
                self._outer = outer
                self._fn = fn
                self._payload = payload

            def execute(self) -> MagicMock:
                if self._fn == "bump_rate_counter":
                    return MagicMock(data=self._outer._bump(self._payload))
                raise AssertionError(f"unexpected rpc {self._fn}")

        return RpcQuery(self, name, params)

    @staticmethod
    def _rpc_key(params: dict[str, Any]) -> str:
        return "|".join(
            [
                str(params["p_scope"]),
                str(params["p_key"]),
                str(params["p_window"]),
                str(params["p_limit"]),
            ]
        )

    def _bump(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        key = self._rpc_key(params)
        if key in self.rpc_results:
            return self.rpc_results[key]

        scope = params["p_scope"]
        rate_key = params["p_key"]
        limit = int(params["p_limit"])
        table = self.tables["rate_counters"]
        matches = [row for row in table.rows if row["scope"] == scope and row["key"] == rate_key]
        count = matches[0]["count"] if matches else 0
        if count >= limit:
            return [{"allowed": False, "retry_after_seconds": 120}]
        if matches:
            matches[0]["count"] = count + 1
        else:
            table.rows.append(
                {
                    "scope": scope,
                    "key": rate_key,
                    "window_start": datetime.now(UTC).isoformat(),
                    "count": 1,
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                }
            )
        return [{"allowed": True, "retry_after_seconds": 0}]


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    clear_rate_limit_config_cache()
    return FakeSupabaseClient()


@pytest.fixture
def guard_client(
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(
        "app.routers.auth_guard.check_and_increment_otp_quota",
        lambda **kwargs: check_and_increment_otp_quota(client=fake_client, **kwargs),
    )
    monkeypatch.setattr(
        "app.routers.auth_guard.check_auth_endpoint_limit",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.core.ratelimit.get_supabase_service_client",
        lambda: MagicMock(client=fake_client),
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def test_cap_breach_raises_429_with_retry_after(fake_client: FakeSupabaseClient) -> None:
    fake_client.rpc_results["otp_number|+260971234567|3600 seconds|5"] = [
        {"allowed": False, "retry_after_seconds": 42}
    ]

    with pytest.raises(AppError) as exc:
        check_and_increment_otp_quota(
            phone="+260971234567",
            ip="203.0.113.1",
            client=fake_client,
            config=RateLimitConfig(
                otp_cap_per_number_hour=5,
                otp_cap_per_ip_day=20,
                otp_resend_cooldown_base_seconds=30,
                otp_resend_cooldown_max_seconds=900,
                auth_endpoint_cap_per_ip_minute=60,
            ),
        )

    assert exc.value.http_status == 429
    assert exc.value.code == "rate_limited"
    assert exc.value.details["retry_after"] == 42
    assert exc.value.details["message_key"] == "auth.errors.otp_number_limit"


def test_endpoint_returns_429_envelope(
    guard_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.rpc_results["otp_number|+260971234567|3600 seconds|5"] = [
        {"allowed": False, "retry_after_seconds": 17}
    ]

    response = guard_client.post(
        "/auth/guard/otp-quota",
        json={"phone": "+260971234567"},
        headers={"x-forwarded-for": "203.0.113.1"},
    )

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["details"]["retry_after"] == 17


def test_per_number_and_per_ip_independence(fake_client: FakeSupabaseClient) -> None:
    calls: list[tuple[str, str]] = []
    original_bump = fake_client._bump
    fake_client.rpc_results.clear()

    def custom_bump(params: dict[str, Any]) -> list[dict[str, Any]]:
        calls.append((params["p_scope"], params["p_key"]))
        if params["p_scope"] == "otp_number" and params["p_key"] == "+260971111111":
            return [{"allowed": False, "retry_after_seconds": 30}]
        return original_bump(params)

    fake_client._bump = custom_bump  # type: ignore[method-assign]

    with pytest.raises(AppError) as exc:
        check_and_increment_otp_quota(
            phone="+260971111111",
            ip="198.51.100.9",
            client=fake_client,
            config=RateLimitConfig(
                otp_cap_per_number_hour=1,
                otp_cap_per_ip_day=20,
                otp_resend_cooldown_base_seconds=30,
                otp_resend_cooldown_max_seconds=900,
                auth_endpoint_cap_per_ip_minute=60,
            ),
        )

    assert exc.value.details["message_key"] == "auth.errors.otp_number_limit"
    assert calls[0] == ("otp_number", "+260971111111")

    calls.clear()
    check_and_increment_otp_quota(
        phone="+260972222222",
        ip="198.51.100.9",
        client=fake_client,
        config=RateLimitConfig(
            otp_cap_per_number_hour=1,
            otp_cap_per_ip_day=1,
            otp_resend_cooldown_base_seconds=30,
            otp_resend_cooldown_max_seconds=900,
            auth_endpoint_cap_per_ip_minute=60,
        ),
    )
    assert ("otp_number", "+260972222222") in calls
    assert ("otp_ip", "198.51.100.9") in calls


def test_exponential_cooldown_grows() -> None:
    config = RateLimitConfig(
        otp_cap_per_number_hour=5,
        otp_cap_per_ip_day=20,
        otp_resend_cooldown_base_seconds=30,
        otp_resend_cooldown_max_seconds=900,
        auth_endpoint_cap_per_ip_minute=60,
    )
    assert compute_resend_cooldown_seconds(1, config) == 30
    assert compute_resend_cooldown_seconds(2, config) == 60
    assert compute_resend_cooldown_seconds(3, config) == 120
    assert compute_resend_cooldown_seconds(10, config) == 900


def test_active_cooldown_blocks_resend(fake_client: FakeSupabaseClient) -> None:
    future = (datetime.now(UTC) + timedelta(seconds=45)).isoformat()
    fake_client.tables["rate_counters"].rows.append(
        {
            "scope": "otp_number",
            "key": "+260970000000:cooldown",
            "window_start": datetime.now(UTC).isoformat(),
            "count": 2,
            "expires_at": future,
        }
    )

    allowed, retry_after = check_active_cooldown(phone="+260970000000", client=fake_client)
    assert allowed is False
    assert retry_after >= 1


def test_window_expiry_restores_allowance(fake_client: FakeSupabaseClient) -> None:
    allowed, _ = bump_rate_counter(
        scope="otp_number",
        key="+260973333333",
        window=timedelta(hours=1),
        limit=5,
        client=fake_client,
    )
    assert allowed is True

    fake_client.rpc_results["otp_number|+260973333333|3600 seconds|5"] = [
        {"allowed": True, "retry_after_seconds": 0}
    ]
    allowed, _ = bump_rate_counter(
        scope="otp_number",
        key="+260973333333",
        window=timedelta(hours=1),
        limit=5,
        client=fake_client,
    )
    assert allowed is True


def test_load_rate_limit_config_reads_platform_config(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["platform_config"].rows.append(
        {"key": "otp_cap_per_number_hour", "value": 7}
    )
    config = load_rate_limit_config(fake_client)
    assert config.otp_cap_per_number_hour == 7


def test_raise_rate_limited_shape() -> None:
    with pytest.raises(AppError) as exc:
        raise_rate_limited(retry_after=0, message_key="auth.errors.rate_limited")
    assert exc.value.details["retry_after"] == 1
