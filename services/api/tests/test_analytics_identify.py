"""Convergeo Intelligence 1A-08: POST /analytics/identify + link purge (DB-free).

Live-DB behaviour (idempotent upsert, cascade, purge) is in
``tests/rls/test_analytics_session_links_db.py``.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.main import create_app
from app.routers import analytics_identify as mod
from app.routers import internal_analytics as internal_mod
from app.services.analytics import flags as analytics_flags
from app.services.analytics import session_links
from app.services.analytics.retention import V2RetentionResult
from app.services.orders.audit import SqlResult
from fastapi import FastAPI
from fastapi.testclient import TestClient

USER = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def as_customer(app: FastAPI) -> None:
    async def _user() -> CurrentUser:
        return CurrentUser(id=USER, roles=frozenset({"customer"}), token="t")

    app.dependency_overrides[get_current_user] = _user


@pytest.fixture
def link(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(mod, "link_session", mock)
    monkeypatch.setattr(mod, "bump_rate_counter", MagicMock(return_value=(True, 0)))
    return mock


@pytest.fixture
def flag_on() -> None:
    analytics_flags.override_for_tests(analytics_flags.COLLECT_FLAG, True)


def test_anonymous_caller_is_rejected(client: TestClient, flag_on: None, link: MagicMock) -> None:
    resp = client.post("/analytics/identify", json={"session_id": SESSION})
    assert resp.status_code == 401
    link.assert_not_called()


def test_links_session_for_authenticated_customer(
    client: TestClient, as_customer: None, flag_on: None, link: MagicMock
) -> None:
    resp = client.post("/analytics/identify", json={"session_id": SESSION})
    assert resp.status_code == 200
    assert resp.json() == {"linked": True, "skipped": None}
    link.assert_called_once_with(user_id=USER, session_id=SESSION)


def test_flag_off_is_a_noop(client: TestClient, as_customer: None, link: MagicMock) -> None:
    resp = client.post("/analytics/identify", json={"session_id": SESSION})
    assert resp.status_code == 200
    assert resp.json() == {"linked": False, "skipped": "flag_off"}
    link.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [{"X-Analytics-Consent": "denied"}, {"Sec-GPC": "1"}],
)
def test_opted_out_visitor_is_refused(
    client: TestClient,
    as_customer: None,
    flag_on: None,
    link: MagicMock,
    headers: dict[str, str],
) -> None:
    resp = client.post("/analytics/identify", json={"session_id": SESSION}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "analytics.opted_out"
    link.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"session_id": "not-a-uuid"},
        {"session_id": SESSION, "user_id": USER},
        {"session_id": SESSION, "email": "a@b.co"},
        {"session_id": 123},
    ],
)
def test_strict_body_rejects_anything_but_a_session_uuid(
    client: TestClient, as_customer: None, flag_on: None, link: MagicMock, body: dict[str, object]
) -> None:
    assert client.post("/analytics/identify", json=body).status_code == 422
    link.assert_not_called()


def test_rate_limited(
    client: TestClient,
    as_customer: None,
    flag_on: None,
    link: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "bump_rate_counter", MagicMock(return_value=(False, 30)))
    resp = client.post("/analytics/identify", json={"session_id": SESSION})
    assert resp.status_code == 429
    link.assert_not_called()


def test_db_failure_is_503_not_500(
    client: TestClient, as_customer: None, flag_on: None, link: MagicMock
) -> None:
    link.side_effect = RuntimeError("boom")
    assert client.post("/analytics/identify", json={"session_id": SESSION}).status_code == 503


class _FakeDb:
    """In-memory stand-in for the ON CONFLICT upsert (session_id is the primary key)."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}
        self.scripts: list[str] = []

    def run(self, script: str) -> SqlResult:
        self.scripts.append(script)
        assert "ON CONFLICT (session_id)" in script
        session = SESSION if SESSION in script else "other"
        user = USER if f"'{USER}'::uuid" in script else "other-user"
        if session in self.rows and self.rows[session] != user:
            return SqlResult(ok=True, rows=[])
        self.rows[session] = user
        return SqlResult(ok=True, rows=["1"])


def test_link_session_is_idempotent_and_first_claim_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    monkeypatch.setattr(session_links, "run_sql_script", db.run)
    assert session_links.link_session(user_id=USER, session_id=SESSION) is True
    assert session_links.link_session(user_id=USER, session_id=SESSION) is True
    assert db.rows == {SESSION: USER}  # one row, no duplicate
    other = "33333333-3333-4333-8333-333333333333"
    assert session_links.link_session(user_id=other, session_id=SESSION) is False
    assert db.rows == {SESSION: USER}


def test_link_session_raises_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_links, "run_sql_script", lambda _s: SqlResult(ok=False, rows=[], error="x")
    )
    with pytest.raises(RuntimeError):
        session_links.link_session(user_id=USER, session_id=SESSION)


def test_purge_deletes_links_older_than_30_days(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def fake_run(script: str) -> SqlResult:
        captured.append(script)
        return SqlResult(ok=True, rows=["3"])

    monkeypatch.setattr("app.services.analytics.retention.run_sql_script", fake_run)
    deleted, complete = session_links.purge_expired_links(
        datetime(2026, 12, 15, 12, 0, tzinfo=UTC), batch_size=100
    )
    assert (deleted, complete) == (3, True)
    assert "DELETE FROM public.analytics_session_links" in captured[0]
    assert "2026-11-15T12:00:00+00:00" in captured[0]  # now - 30 days
    assert "LIMIT 100" in captured[0]


def test_retention_tick_purges_links_only_when_rollups_flag_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = {"X-Internal-Token": "dev-internal-analytics"}
    purge = MagicMock(return_value=(4, True))
    monkeypatch.setattr(internal_mod, "purge_expired_links", purge)
    monkeypatch.setattr(
        internal_mod,
        "sweep_v2_retention",
        MagicMock(return_value=V2RetentionResult(5, 7, 1, complete=True)),
    )
    off = client.post("/internal/analytics/v2-retention-tick", headers=token)
    assert off.json() == {"skipped": "flag_off"}
    purge.assert_not_called()

    analytics_flags.override_for_tests(analytics_flags.ROLLUPS_FLAG, True)
    on = client.post("/internal/analytics/v2-retention-tick", headers=token)
    assert on.json()["session_links_purged"] == 4
    assert on.json()["complete"] is True
