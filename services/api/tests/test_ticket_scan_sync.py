from __future__ import annotations

import hashlib
import hmac
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.ticket_scan_sync import compute_horizon_windows
from app.routers.ticket_verify import current_window, window_sig
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EVENT_A_ID = "e1000000-0000-0000-0000-000000000001"
EVENT_B_ID = "e1000000-0000-0000-0000-000000000002"
INSTANCE_A_ID = "i1000000-0000-0000-0000-000000000001"
TICKET_TYPE_ID = "t1000000-0000-0000-0000-000000000001"
TICKET_1_ID = "tk100000-0000-0000-0000-000000000001"
TICKET_2_ID = "tk100000-0000-0000-0000-000000000002"
ORDER_ITEM_1_ID = "oi100000-0000-0000-0000-000000000001"
ORDER_ITEM_2_ID = "oi100000-0000-0000-0000-000000000002"
HOLDER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False

    def select(self, columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        rows = self._apply_filters(self._parent.rows)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in set(value):
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._matches(row)]


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, []).select(columns)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "events": FakeTable(),
            "event_instances": FakeTable(),
            "tickets": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _future_iso(hours: int = 48) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def _seed_vendors(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {"id": VENDOR_A_ID, "owner_user_id": USER_A_ID},
            {"id": VENDOR_B_ID, "owner_user_id": USER_B_ID},
        ]
    )


def _seed_event(
    fake: FakeSupabaseClient,
    *,
    event_id: str = EVENT_A_ID,
    vendor_id: str = VENDOR_A_ID,
    instance_id: str = INSTANCE_A_ID,
    starts_at: str | None = None,
) -> None:
    fake.tables["events"].rows.append({"id": event_id, "organiser_vendor_id": vendor_id})
    fake.tables["event_instances"].rows.append(
        {
            "id": instance_id,
            "event_id": event_id,
            "starts_at": starts_at or _future_iso(),
            "capacity": 100,
        }
    )


def _seed_tickets(
    fake: FakeSupabaseClient,
    *,
    instance_id: str = INSTANCE_A_ID,
) -> None:
    fake.tables["tickets"].rows.extend(
        [
            {
                "id": TICKET_1_ID,
                "instance_id": instance_id,
                "status": "issued",
                "order_item_id": ORDER_ITEM_1_ID,
                "qr_secret": "secret-one",
                "pin_hash": "pinhash-one",
            },
            {
                "id": TICKET_2_ID,
                "instance_id": instance_id,
                "status": "transferred",
                "order_item_id": ORDER_ITEM_2_ID,
                "qr_secret": "secret-two",
                "pin_hash": None,
            },
            # not issued/paid -- must never appear in the sync payload
            {
                "id": "tk100000-0000-0000-0000-000000000003",
                "instance_id": instance_id,
                "status": "void",
                "order_item_id": "oi100000-0000-0000-0000-000000000003",
                "qr_secret": "secret-three",
                "pin_hash": None,
            },
            # unpaid hold -- order_item_id is NULL, must be excluded
            {
                "id": "tk100000-0000-0000-0000-000000000004",
                "instance_id": instance_id,
                "status": "issued",
                "order_item_id": None,
                "qr_secret": "secret-four",
                "pin_hash": None,
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

    def roles(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return frozenset({"vendor"})

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
    monkeypatch.setattr("app.core.auth._load_user_roles", roles)


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.deps.get_supabase_client", lambda: iter([service_wrapper]))
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def organiser_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    _seed_vendors(fake_client)
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sync_url(event_id: str = EVENT_A_ID, instance_id: str = INSTANCE_A_ID) -> str:
    return f"/events/{event_id}/instances/{instance_id}/scan-sync"


class TestScanSyncPayload:
    def test_sync_returns_window_sigs_without_secret(
        self, organiser_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_event(fake_client)
        _seed_tickets(fake_client)

        response = organiser_client.get(_sync_url(), headers=_auth_headers(TOKEN_A))

        assert response.status_code == 200
        payload = response.json()
        raw_text = response.text

        # The raw qr_secret must never appear anywhere in the response body.
        assert "secret-one" not in raw_text
        assert "secret-two" not in raw_text
        assert "qr_secret" not in raw_text

        tickets = {item["ticket_id"]: item for item in payload["tickets"]}
        # Only issued/transferred tickets with a paid order_item are synced.
        assert set(tickets.keys()) == {TICKET_1_ID, TICKET_2_ID}
        assert tickets[TICKET_1_ID]["pin_hash_present"] is True
        assert tickets[TICKET_2_ID]["pin_hash_present"] is False
        assert len(tickets[TICKET_1_ID]["window_sigs"]) > 0

    def test_sync_sig_parity_with_verify_window_sig(
        self, organiser_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        starts_at = datetime(2026, 8, 1, 18, 0, 0, tzinfo=UTC)
        _seed_event(fake_client, starts_at=starts_at.isoformat())
        _seed_tickets(fake_client)

        response = organiser_client.get(_sync_url(), headers=_auth_headers(TOKEN_A))
        assert response.status_code == 200
        payload = response.json()

        horizon_start = payload["horizon_start_window"]
        expected_start, expected_end = compute_horizon_windows(starts_at)
        assert horizon_start == expected_start
        assert payload["horizon_end_window"] == expected_end

        ticket_one = next(t for t in payload["tickets"] if t["ticket_id"] == TICKET_1_ID)
        # Spot-check a handful of positions against the same window_sig the
        # online verify endpoint uses -- parity is the whole point.
        for offset in (0, 5, len(ticket_one["window_sigs"]) - 1):
            window = horizon_start + offset
            assert ticket_one["window_sigs"][offset] == window_sig("secret-one", window)

    def test_sync_excludes_unavailable_secret(
        self, organiser_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_event(fake_client)
        fake_client.tables["tickets"].rows.append(
            {
                "id": "tk100000-0000-0000-0000-000000000009",
                "instance_id": INSTANCE_A_ID,
                "status": "issued",
                "order_item_id": "oi100000-0000-0000-0000-000000000009",
                "qr_secret": None,
                "pin_hash": None,
            }
        )
        response = organiser_client.get(_sync_url(), headers=_auth_headers(TOKEN_A))
        assert response.status_code == 200
        ticket_ids = {t["ticket_id"] for t in response.json()["tickets"]}
        assert "tk100000-0000-0000-0000-000000000009" not in ticket_ids


class TestScanSyncOrganiserScope:
    def test_cross_organiser_returns_403(
        self, organiser_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_event(fake_client, event_id=EVENT_A_ID, vendor_id=VENDOR_A_ID)
        _seed_tickets(fake_client)

        response = organiser_client.get(_sync_url(), headers=_auth_headers(TOKEN_B))

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_unknown_event_returns_404(
        self, organiser_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        response = organiser_client.get(
            _sync_url(event_id="e1000000-0000-0000-0000-0000000000ff"),
            headers=_auth_headers(TOKEN_A),
        )
        assert response.status_code == 404

    def test_instance_not_belonging_to_event_returns_404(
        self, organiser_client: TestClient, fake_client: FakeSupabaseClient
    ) -> None:
        _seed_event(fake_client, event_id=EVENT_A_ID, vendor_id=VENDOR_A_ID)
        _seed_event(
            fake_client,
            event_id=EVENT_B_ID,
            vendor_id=VENDOR_B_ID,
            instance_id="i1000000-0000-0000-0000-000000000002",
        )
        response = organiser_client.get(
            _sync_url(event_id=EVENT_A_ID, instance_id="i1000000-0000-0000-0000-000000000002"),
            headers=_auth_headers(TOKEN_A),
        )
        assert response.status_code == 404


class TestWindowSigHelpers:
    def test_window_sig_matches_hmac_reference(self) -> None:
        window = current_window(datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC))
        expected = hmac.new(b"my-secret", str(window).encode("utf-8"), hashlib.sha256).hexdigest()[
            :16
        ]
        assert window_sig("my-secret", window) == expected

    def test_compute_horizon_windows_is_bounded_and_ordered(self) -> None:
        starts_at = datetime(2026, 7, 10, 18, 0, 0, tzinfo=UTC)
        start_window, end_window = compute_horizon_windows(starts_at)
        assert start_window < end_window
        # Horizon before doors + after start should stay within a single day.
        assert (end_window - start_window) * 60 <= 24 * 3600
