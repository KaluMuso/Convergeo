"""Task 2: POST /analytics/collect beacon ingest.

DB-free — ``record_event`` is patched, so these assert the endpoint's own logic:
batch caps, the persist/skip allowlist, session/user stitching, per-event
fire-and-forget, and rate-limit fail-open. The real anonymization guard lives in
``events.record_event`` (test_analytics_unify.py); here we only assert the endpoint's
handling of its raises.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.routers import analytics_collect as collect_mod
from fastapi.testclient import TestClient

SESSION_ID = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
USER_ID = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
def rec(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value={"id": "x", "event_type": "product_view", "created_at": "t"})
    monkeypatch.setattr(collect_mod, "record_event", mock)
    return mock


def _post(
    client: TestClient, payload: dict[str, Any], headers: dict[str, str] | None = None
) -> Any:
    return client.post("/analytics/collect", json=payload, headers=headers or {})


class TestCollect:
    def test_persists_product_view_with_session(self, client: TestClient, rec: MagicMock) -> None:
        resp = _post(
            client,
            {
                "session_id": SESSION_ID,
                "events": [{"event": "product_view", "props": {"product_id": "p1"}, "ts": 123}],
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 1, "skipped": 0, "rejected": 0}
        rec.assert_called_once()
        kwargs = rec.call_args.kwargs
        assert kwargs["event_type"] == "product_view"
        assert kwargs["session_id"] == SESSION_ID
        assert kwargs["user_id"] is None
        assert kwargs["props"] == {"product_id": "p1"}

    def test_skips_server_recorded_events(self, client: TestClient, rec: MagicMock) -> None:
        resp = _post(
            client,
            {
                "events": [
                    {"event": "cart_add", "props": {}},
                    {"event": "search", "props": {}},
                    {"event": "order_placed", "props": {}},
                ]
            },
        )
        assert resp.json() == {"accepted": 0, "skipped": 3, "rejected": 0}
        rec.assert_not_called()  # already recorded authoritatively server-side (no double-count)

    def test_mixed_batch(self, client: TestClient, rec: MagicMock) -> None:
        resp = _post(
            client,
            {
                "events": [
                    {"event": "product_view", "props": {"product_id": "p1"}},
                    {"event": "cart_add", "props": {}},
                ]
            },
        )
        assert resp.json() == {"accepted": 1, "skipped": 1, "rejected": 0}

    def test_oversized_batch_rejected_413(self, client: TestClient, rec: MagicMock) -> None:
        events = [{"event": "product_view", "props": {}} for _ in range(21)]
        resp = _post(client, {"events": events})
        assert resp.status_code == 413
        rec.assert_not_called()

    def test_invalid_session_id_dropped(self, client: TestClient, rec: MagicMock) -> None:
        _post(
            client,
            {"session_id": "not-a-uuid", "events": [{"event": "product_view", "props": {}}]},
        )
        assert rec.call_args.kwargs["session_id"] is None

    def test_bad_event_counted_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(**_k: Any) -> Any:
            raise ValueError("Raw PII key not allowed in analytics props")

        monkeypatch.setattr(collect_mod, "record_event", _raise)
        resp = _post(client, {"events": [{"event": "product_view", "props": {"phone": "x"}}]})
        assert resp.status_code == 200
        assert resp.json() == {"accepted": 0, "skipped": 0, "rejected": 1}

    def test_db_failure_is_fire_and_forget(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(**_k: Any) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(collect_mod, "record_event", _raise)
        resp = _post(client, {"events": [{"event": "product_view", "props": {}}]})
        assert resp.status_code == 200  # never 500s the batch
        assert resp.json()["rejected"] == 1

    def test_authed_stitches_user_id(
        self, client: TestClient, rec: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_user(_request: Any, _settings: Any) -> Any:
            return SimpleNamespace(id=USER_ID)

        monkeypatch.setattr(collect_mod, "get_current_user", _fake_user)
        _post(
            client,
            {"session_id": SESSION_ID, "events": [{"event": "product_view", "props": {}}]},
            headers={"Authorization": "Bearer tok"},
        )
        kwargs = rec.call_args.kwargs
        assert kwargs["user_id"] == USER_ID  # forward identity stitch: session_id ↔ user_id
        assert kwargs["session_id"] == SESSION_ID

    def test_rate_limited_returns_429(
        self, client: TestClient, rec: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(collect_mod, "bump_rate_counter", lambda **_k: (False, 30))
        resp = _post(client, {"events": [{"event": "product_view", "props": {}}]})
        assert resp.status_code == 429

    def test_rate_limiter_failure_is_open(
        self, client: TestClient, rec: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(**_k: Any) -> Any:
            raise RuntimeError("rate store down")

        monkeypatch.setattr(collect_mod, "bump_rate_counter", _boom)
        resp = _post(client, {"events": [{"event": "product_view", "props": {}}]})
        assert resp.status_code == 200  # fail-open: analytics is non-critical
        assert resp.json()["accepted"] == 1
