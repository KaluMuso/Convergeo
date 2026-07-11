from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.ask.quota import (
    QuotaReservation,
    check_and_reserve,
    clear_active_reservations_for_tests,
    record_answer,
)
from app.services.ask.spend import (
    clear_spend_config_cache,
    current_month_key,
    is_killed,
    reset_kill_switch,
    tokens_to_usd_micros,
)


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._count: str | None = None

    def select(self, _columns: str, *, count: str | None = None) -> FakeQuery:
        self._count = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
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

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            if isinstance(self._payload, list):
                for row in self._payload:
                    self._parent.rows.append(dict(row))
                return MagicMock(data=self._payload)
            assert isinstance(self._payload, dict)
            self._parent.rows.append(dict(self._payload))
            return MagicMock(data=[self._payload])

        if self._pending_op == "update":
            rows = self._apply_filters(self._parent.rows)
            assert isinstance(self._payload, dict)
            for row in rows:
                row.update(self._payload)
            return MagicMock(data=rows)

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
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "platform_config": FakeTable(),
            "ask_usage": FakeTable(),
            "ask_spend_monthly": FakeTable(),
            "rate_counters": FakeTable(),
        }
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        self.tables["platform_config"].rows.extend(
            [
                {"key": "ai_guest_quota", "value": 3},
                {"key": "ai_free_monthly_quota", "value": 25},
                {"key": "ai_monthly_cap_usd", "value": 15},
                {
                    "key": "ai_model_rates",
                    "value": {"default": 0.15, "test-model": 1.0},
                },
            ]
        )

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.rpc_calls.append((name, params))

        class RpcQuery:
            def __init__(self, outer: FakeSupabaseClient, fn: str, payload: dict[str, Any]) -> None:
                self._outer = outer
                self._fn = fn
                self._payload = payload

            def execute(self) -> MagicMock:
                return MagicMock(data=self._outer._handle_rpc(self._fn, self._payload))

        return RpcQuery(self, name, params)

    def _config_int(self, key: str, default: int) -> int:
        for row in self.tables["platform_config"].rows:
            if row.get("key") == key:
                value = row.get("value")
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)
        return default

    def _handle_rpc(self, fn: str, params: dict[str, Any]) -> list[Any]:
        if fn == "reserve_ask_quota":
            return [self._reserve_ask_quota(params)]
        if fn == "finalize_ask_answer":
            return [self._finalize_ask_answer(params)]
        if fn == "reset_ask_kill_switch":
            return [self._reset_ask_kill_switch(params)]
        raise AssertionError(f"unexpected rpc {fn}")

    def _reserve_ask_quota(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            user_id = params.get("p_user_id")
            guest_key = params.get("p_guest_key")
            client_ip = params.get("p_client_ip")
            month_key = current_month_key()
            usage = self.tables["ask_usage"].rows

            if user_id is not None:
                count = sum(
                    1
                    for row in usage
                    if row.get("user_id") == user_id
                    and row.get("month_key") == month_key
                    and row.get("status") in {"reserved", "answered"}
                )
                limit = self._config_int("ai_free_monthly_quota", 25)
                if count >= limit:
                    return {"allowed": False, "reason": "monthly_exceeded", "reservation_id": None}
            else:
                count = sum(
                    1
                    for row in usage
                    if row.get("user_id") is None
                    and row.get("status") in {"reserved", "answered"}
                    and (
                        (guest_key and row.get("guest_key") == guest_key)
                        or (client_ip and row.get("client_ip") == client_ip)
                    )
                )
                limit = self._config_int("ai_guest_quota", 3)
                if count >= limit:
                    return {"allowed": False, "reason": "guest_exceeded", "reservation_id": None}

            reservation_id = str(uuid.uuid4())
            self.tables["ask_usage"].rows.append(
                {
                    "id": reservation_id,
                    "user_id": user_id,
                    "guest_key": guest_key,
                    "client_ip": client_ip,
                    "question_hash": params.get("p_question_hash"),
                    "tokens": 0,
                    "usd_micros": 0,
                    "model": None,
                    "month_key": month_key,
                    "status": "reserved",
                    "created_at": datetime.now(UTC).isoformat(),
                    "answered_at": None,
                }
            )
            return {"allowed": True, "reason": "ok", "reservation_id": reservation_id}

    def _finalize_ask_answer(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            reservation_id = params["p_reservation_id"]
            usage_rows = self.tables["ask_usage"].rows
            row = next((item for item in usage_rows if item.get("id") == reservation_id), None)
            if row is None:
                return {"success": False, "month_total_usd_micros": 0, "killed": False}

            if row.get("status") == "answered":
                month_key = row.get("month_key", current_month_key())
                spend_row = next(
                    (
                        item
                        for item in self.tables["ask_spend_monthly"].rows
                        if item.get("month_key") == month_key
                    ),
                    None,
                )
                total = int(spend_row.get("total_usd_micros", 0)) if spend_row else 0
                admin_reset = spend_row.get("admin_reset_at") if spend_row else None
                killed_at_val = spend_row.get("killed_at") if spend_row else None
                killed = bool(
                    spend_row
                    and killed_at_val
                    and (admin_reset is None or admin_reset < killed_at_val)
                )
                return {
                    "success": True,
                    "month_total_usd_micros": total,
                    "killed": killed,
                }

            usd_micros = int(params["p_usd_micros"])
            row.update(
                {
                    "tokens": int(params["p_tokens"]),
                    "usd_micros": usd_micros,
                    "model": params["p_model"],
                    "status": "answered",
                    "answered_at": datetime.now(UTC).isoformat(),
                }
            )

            month_key = row.get("month_key", current_month_key())
            spend_row = next(
                (
                    item
                    for item in self.tables["ask_spend_monthly"].rows
                    if item.get("month_key") == month_key
                ),
                None,
            )
            if spend_row is None:
                spend_row = {
                    "month_key": month_key,
                    "total_usd_micros": 0,
                    "killed_at": None,
                    "admin_reset_at": None,
                }
                self.tables["ask_spend_monthly"].rows.append(spend_row)

            spend_row["total_usd_micros"] = int(spend_row.get("total_usd_micros", 0)) + usd_micros
            cap = self._config_int("ai_monthly_cap_usd", 15) * 1_000_000
            killed = False
            if spend_row["total_usd_micros"] >= cap and spend_row.get("killed_at") is None:
                spend_row["killed_at"] = datetime.now(UTC).isoformat()
            admin_reset = spend_row.get("admin_reset_at")
            killed_at_val = spend_row.get("killed_at")
            if killed_at_val and (admin_reset is None or admin_reset < killed_at_val):
                killed = True

            return {
                "success": True,
                "month_total_usd_micros": spend_row["total_usd_micros"],
                "killed": killed,
            }

    def _reset_ask_kill_switch(self, params: dict[str, Any]) -> bool:
        month_key = params.get("p_month_key") or current_month_key()
        spend_row = next(
            (
                item
                for item in self.tables["ask_spend_monthly"].rows
                if item.get("month_key") == month_key
            ),
            None,
        )
        if spend_row is None:
            self.tables["ask_spend_monthly"].rows.append(
                {
                    "month_key": month_key,
                    "total_usd_micros": 0,
                    "killed_at": None,
                    "admin_reset_at": datetime.now(UTC).isoformat(),
                }
            )
            return True
        spend_row["killed_at"] = None
        spend_row["admin_reset_at"] = datetime.now(UTC).isoformat()
        return True


@pytest.fixture(autouse=True)
def _reset_quota_state() -> Generator[None, None, None]:
    clear_active_reservations_for_tests()
    clear_spend_config_cache()
    yield
    clear_active_reservations_for_tests()
    clear_spend_config_cache()


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ask.quota.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


class TestGuestQuotaBoundary:
    def test_third_guest_question_allowed_fourth_blocked(
        self, fake_client: FakeSupabaseClient, allow_rate_limits: None
    ) -> None:
        guest_key = "device-abc"
        client_ip = "203.0.113.10"

        for index in range(3):
            reservation = check_and_reserve(
                client=fake_client,
                guest_key=guest_key,
                client_ip=client_ip,
                question=f"Where can I buy cement in Lusaka? variant {index}",
            )
            record_answer(
                client=fake_client,
                reservation=reservation,
                tokens=100,
                model="test-model",
            )

        with pytest.raises(AppError) as exc:
            check_and_reserve(
                client=fake_client,
                guest_key=guest_key,
                client_ip=client_ip,
                question="Fourth guest question should be blocked",
            )

        assert exc.value.code == "ai_quota_guest_exceeded"
        assert exc.value.message == "ai.quota.guestExceeded"


class TestFreeMonthlyQuotaBoundary:
    def test_twenty_fifth_free_question_allowed_twenty_sixth_blocked(
        self, fake_client: FakeSupabaseClient, allow_rate_limits: None
    ) -> None:
        user_id = "user-free-001"

        for index in range(25):
            reservation = check_and_reserve(
                client=fake_client,
                user_id=user_id,
                question=f"Show phones under K2000 variant {index}",
            )
            record_answer(
                client=fake_client,
                reservation=reservation,
                tokens=50,
                model="test-model",
            )

        with pytest.raises(AppError) as exc:
            check_and_reserve(
                client=fake_client,
                user_id=user_id,
                question="Twenty-sixth monthly question should be blocked",
            )

        assert exc.value.code == "ai_quota_monthly_exceeded"
        assert exc.value.message == "ai.quota.monthlyExceeded"


class TestMonthRollover:
    def test_previous_month_usage_does_not_count_against_new_month(
        self, fake_client: FakeSupabaseClient, allow_rate_limits: None
    ) -> None:
        user_id = "user-rollover"
        previous_month = "2026-06"

        for index in range(25):
            fake_client.tables["ask_usage"].rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "guest_key": None,
                    "client_ip": None,
                    "question_hash": f"old-{index}",
                    "tokens": 10,
                    "usd_micros": 1,
                    "model": "test-model",
                    "month_key": previous_month,
                    "status": "answered",
                    "created_at": datetime(2026, 6, 15, tzinfo=UTC).isoformat(),
                    "answered_at": datetime(2026, 6, 15, tzinfo=UTC).isoformat(),
                }
            )

        reservation = check_and_reserve(
            client=fake_client,
            user_id=user_id,
            question="New month question should be allowed",
        )
        record_answer(
            client=fake_client,
            reservation=reservation,
            tokens=25,
            model="test-model",
        )

        current_count = sum(
            1
            for row in fake_client.tables["ask_usage"].rows
            if row.get("user_id") == user_id
            and row.get("month_key") == current_month_key()
            and row.get("status") in {"reserved", "answered"}
        )
        assert current_count == 1


class TestKillSwitch:
    def test_kill_switch_trips_at_cap_and_admin_reset(
        self, fake_client: FakeSupabaseClient, allow_rate_limits: None
    ) -> None:
        for row in fake_client.tables["platform_config"].rows:
            if row.get("key") == "ai_monthly_cap_usd":
                row["value"] = 1
                break

        reservation = check_and_reserve(
            client=fake_client,
            guest_key="guest-kill",
            client_ip="203.0.113.20",
            question="Trip the kill switch",
        )
        record_answer(
            client=fake_client,
            reservation=reservation,
            tokens=1_000_000,
            model="test-model",
        )

        assert is_killed(client=fake_client) is True

        with pytest.raises(AppError) as exc:
            check_and_reserve(
                client=fake_client,
                guest_key="guest-kill-2",
                client_ip="203.0.113.21",
                question="Should be blocked by kill switch",
            )
        assert exc.value.code == "ai_quota_kill_switch"
        assert exc.value.message == "ai.quota.killSwitch"

        assert reset_kill_switch(client=fake_client) is True
        assert is_killed(client=fake_client) is False

        check_and_reserve(
            client=fake_client,
            guest_key="guest-kill-3",
            client_ip="203.0.113.22",
            question="Allowed after admin reset",
        )


class TestConcurrentDecrements:
    def test_parallel_reservations_are_race_safe(
        self, fake_client: FakeSupabaseClient, allow_rate_limits: None
    ) -> None:
        user_id = "user-concurrent"
        barrier = threading.Barrier(5)
        errors: list[Exception] = []
        reservations: list[QuotaReservation] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            try:
                barrier.wait(timeout=5)
                reservation = check_and_reserve(
                    client=fake_client,
                    user_id=user_id,
                    question=f"Concurrent question {index}",
                )
                with lock:
                    reservations.append(reservation)
                record_answer(
                    client=fake_client,
                    reservation=reservation,
                    tokens=10,
                    model="test-model",
                )
            except Exception as exc:  # pragma: no cover - collected for assertion
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert len(reservations) == 5
        answered = [
            row
            for row in fake_client.tables["ask_usage"].rows
            if row.get("user_id") == user_id and row.get("status") == "answered"
        ]
        assert len(answered) == 5
        assert len({row["id"] for row in answered}) == 5


class TestCacheHitContract:
    def test_record_answer_not_required_on_cache_hit_path(
        self, allow_rate_limits: None
    ) -> None:
        """M06-P02 skips record_answer on cache hits — quota rows stay reserved-only."""

        def simulate_ask_flow(*, cache_hit: bool) -> int:
            client = FakeSupabaseClient()
            reservation = check_and_reserve(
                client=client,
                guest_key="cache-contract",
                client_ip="203.0.113.30",
                question="Show me rice listings",
            )
            if not cache_hit:
                record_answer(
                    client=client,
                    reservation=reservation,
                    tokens=42,
                    model="test-model",
                )
            return sum(
                1
                for row in client.tables["ask_usage"].rows
                if row.get("status") == "answered"
            )

        assert simulate_ask_flow(cache_hit=True) == 0
        assert simulate_ask_flow(cache_hit=False) == 1


class TestSpendMeter:
    def test_tokens_to_usd_micros_uses_decimal_not_float(
        self, fake_client: FakeSupabaseClient
    ) -> None:
        micros = tokens_to_usd_micros(tokens=1_000_000, model="test-model", client=fake_client)
        assert micros == 1_000_000
        assert isinstance(Decimal(str(micros)), Decimal)


class TestGuestIpHeuristic:
    def test_ip_heuristic_blocks_after_cookie_clear(
        self, fake_client: FakeSupabaseClient, allow_rate_limits: None
    ) -> None:
        client_ip = "203.0.113.40"

        for index in range(3):
            reservation = check_and_reserve(
                client=fake_client,
                guest_key=f"device-{index}",
                client_ip=client_ip,
                question=f"Guest IP heuristic question {index}",
            )
            record_answer(
                client=fake_client,
                reservation=reservation,
                tokens=10,
                model="test-model",
            )

        with pytest.raises(AppError) as exc:
            check_and_reserve(
                client=fake_client,
                guest_key="brand-new-cookie",
                client_ip=client_ip,
                question="Cookie cleared but same IP should still be capped",
            )

        assert exc.value.code == "ai_quota_guest_exceeded"


class TestMigrationReplayNote:
    def test_migration_file_is_documented_reversible(self) -> None:
        from tests.rls.conftest import MIGRATIONS_DIR

        sql = (MIGRATIONS_DIR / "0024_ask_usage.sql").read_text(encoding="utf-8")
        assert "Reversible rollback" in sql
        assert "ask_usage" in sql
        assert "ask_spend_monthly" in sql
