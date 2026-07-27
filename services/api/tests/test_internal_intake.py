"""M18-P07 — internal intake operations: sweeps, retention, metrics.

The properties under test are the ones an operator has to be able to trust
without reading workflow JSON:

* the endpoints are unreachable without the shared token;
* expiry goes through P01's **guarded transition** (so it is audited) and never
  touches a terminal session;
* the retention sweep **minimises** rather than deletes — the message row, its
  provider id and its disposition survive, only ``raw_excerpt`` is cleared;
  deleting the row would silently re-open that message to reprocessing;
* a **redeemed** deep link is kept as evidence a vendor opened the session, while
  an expired unredeemed one is discarded;
* every sweep is idempotent: a second run finds nothing left to do;
* nothing here writes to the outbox or sends anything — the operational lane is
  as inbound-only as the ingestion lane.
"""

from __future__ import annotations

import ast
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.intake import state_machine
from fastapi.testclient import TestClient

VALID_TOKEN = "dev-internal-intake"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BINDING_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SESSION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
FRESH_SESSION_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
TERMINAL_SESSION_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


def _past() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).isoformat()


def _future() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


# --- Fake Supabase ----------------------------------------------------------
class FakeNot:
    def __init__(self, query: FakeQuery) -> None:
        self._query = query

    def is_(self, column: str, value: Any) -> FakeQuery:
        self._query.filters.append(("not_is", column, value))
        return self._query


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self.filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    @property
    def not_(self) -> FakeNot:
        return FakeNot(self)

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self.filters.append(("in", column, values))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("lt", column, value))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("is", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self.filters:
            actual = row.get(column)
            if op == "eq" and actual != value:
                return False
            if op == "in" and actual not in value:
                return False
            if op == "lt":
                if actual is None or str(actual) >= str(value):
                    return False
            if op == "is" and value in ("null", None) and actual is not None:
                return False
            if op == "not_is" and value in ("null", None) and actual is None:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"row-{len(self._parent.rows)}-{self._parent.name}")
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._op == "update":
            assert self._payload is not None
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        if self._op == "delete":
            kept = [row for row in self._parent.rows if not self._match(row)]
            removed = len(self._parent.rows) - len(kept)
            self._parent.rows[:] = kept
            return MagicMock(data=[{}] * removed)

        rows = [dict(row) for row in self._parent.rows if self._match(row)]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    supabase = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = supabase
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.internal_intake.get_supabase_client", lambda: wrapper)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("INTERNAL_INTAKE_TOKEN", raising=False)
    return supabase


def _headers() -> dict[str, str]:
    return {"X-Internal-Token": VALID_TOKEN}


def _seed_sessions(fake: FakeSupabaseClient) -> None:
    fake.table("intake_sessions").rows.extend(
        [
            {
                "id": SESSION_ID,
                "vendor_id": VENDOR_ID,
                "binding_id": BINDING_ID,
                "status": state_machine.NEEDS_DETAILS,
                "expires_at": _past(),
                "listing_id": None,
            },
            {
                "id": FRESH_SESSION_ID,
                "vendor_id": VENDOR_ID,
                "binding_id": BINDING_ID,
                "status": state_machine.COLLECTING,
                "expires_at": _future(),
                "listing_id": None,
            },
            {
                # Already terminal AND past its expiry — must not be touched.
                "id": TERMINAL_SESSION_ID,
                "vendor_id": VENDOR_ID,
                "binding_id": BINDING_ID,
                "status": state_machine.APPROVED,
                "expires_at": _past(),
                "listing_id": "99999999-9999-9999-9999-999999999999",
            },
        ]
    )
    fake.table("intake_events")


# --- Auth -------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        "/internal/intake/expire-sessions",
        "/internal/intake/purge-messages",
        "/internal/intake/purge-links",
    ],
)
def test_post_endpoints_require_the_token(
    client: TestClient, fake: FakeSupabaseClient, path: str
) -> None:
    assert client.post(path).status_code == 401


def test_metrics_requires_the_token(client: TestClient, fake: FakeSupabaseClient) -> None:
    assert client.get("/internal/intake/metrics").status_code == 401


def test_wrong_token_is_rejected(client: TestClient, fake: FakeSupabaseClient) -> None:
    response = client.post(
        "/internal/intake/expire-sessions", headers={"X-Internal-Token": "nope"}
    )
    assert response.status_code == 401


def test_strict_env_without_a_secret_fails_closed(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production must not fall back to the well-known dev default."""
    monkeypatch.setenv("ENV", "production")
    response = client.post("/internal/intake/expire-sessions", headers=_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "configuration_error"


# --- Session expiry ---------------------------------------------------------
def test_expire_sweep_expires_only_stale_non_terminal_sessions(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    _seed_sessions(fake)

    body = client.post("/internal/intake/expire-sessions", headers=_headers()).json()
    assert body["expired"] == 1

    by_id = {row["id"]: row for row in fake.table("intake_sessions").rows}
    assert by_id[SESSION_ID]["status"] == state_machine.EXPIRED
    # Not yet due.
    assert by_id[FRESH_SESSION_ID]["status"] == state_machine.COLLECTING
    # Terminal and past expiry — left alone, not force-updated.
    assert by_id[TERMINAL_SESSION_ID]["status"] == state_machine.APPROVED


def test_expire_sweep_writes_an_audit_row(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    """Expiry goes through the guarded transition, so it is auditable."""
    _seed_sessions(fake)
    client.post("/internal/intake/expire-sessions", headers=_headers())

    events = fake.table("intake_events").rows
    transitions = [row for row in events if row.get("kind") == "transition"]
    assert len(transitions) == 1
    assert transitions[0]["to_status"] == state_machine.EXPIRED
    assert transitions[0]["session_id"] == SESSION_ID


def test_expire_sweep_is_idempotent(client: TestClient, fake: FakeSupabaseClient) -> None:
    _seed_sessions(fake)
    first = client.post("/internal/intake/expire-sessions", headers=_headers()).json()
    second = client.post("/internal/intake/expire-sessions", headers=_headers()).json()

    assert first["expired"] == 1
    assert second["scanned"] == 0
    assert second["expired"] == 0
    # And no second audit row for the same session.
    transitions = [
        row for row in fake.table("intake_events").rows if row.get("kind") == "transition"
    ]
    assert len(transitions) == 1


def test_expire_sweep_counts_a_lost_race_as_skipped(
    client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another writer getting there first is a normal outcome, not an error."""
    _seed_sessions(fake)
    from app.errors import AppError

    def conflict(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AppError(
            code="intake_transition_conflict", message="raced", http_status=409
        )

    monkeypatch.setattr("app.routers.internal_intake.state_machine.expire", conflict)

    body = client.post("/internal/intake/expire-sessions", headers=_headers()).json()
    assert body["expired"] == 0
    assert body["skipped"] == 1


# --- Retention --------------------------------------------------------------
def test_purge_minimises_content_but_keeps_the_row(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    """D35 §12: clear raw_excerpt, keep the id/kind that make replay-dedupe work."""
    fake.table("intake_messages").rows.append(
        {
            "id": "msg-1",
            "session_id": SESSION_ID,
            "provider_message_id": "waha-abc",
            "kind": "text",
            "raw_excerpt": "Samsung fridge K3500",
            "purge_after": _past(),
        }
    )

    body = client.post("/internal/intake/purge-messages", headers=_headers()).json()
    assert body["purged"] == 1

    rows = fake.table("intake_messages").rows
    assert len(rows) == 1, "the message row itself must survive minimisation"
    assert rows[0]["raw_excerpt"] is None
    assert rows[0]["provider_message_id"] == "waha-abc"
    assert rows[0]["kind"] == "text"


def test_purge_leaves_content_inside_the_retention_window(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    fake.table("intake_messages").rows.append(
        {
            "id": "msg-1",
            "session_id": SESSION_ID,
            "provider_message_id": "waha-abc",
            "kind": "text",
            "raw_excerpt": "still within window",
            "purge_after": _future(),
        }
    )

    body = client.post("/internal/intake/purge-messages", headers=_headers()).json()
    assert body["purged"] == 0
    assert fake.table("intake_messages").rows[0]["raw_excerpt"] == "still within window"


def test_purge_is_idempotent(client: TestClient, fake: FakeSupabaseClient) -> None:
    fake.table("intake_messages").rows.append(
        {
            "id": "msg-1",
            "session_id": SESSION_ID,
            "provider_message_id": "waha-abc",
            "kind": "text",
            "raw_excerpt": "Samsung fridge K3500",
            "purge_after": _past(),
        }
    )
    client.post("/internal/intake/purge-messages", headers=_headers())
    second = client.post("/internal/intake/purge-messages", headers=_headers()).json()
    # Already-nulled rows are excluded by the not-null filter, so nothing is rescanned.
    assert second["scanned"] == 0


# --- Deep links -------------------------------------------------------------
def test_link_sweep_deletes_expired_unredeemed_links_only(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    fake.table("intake_deep_links").rows.extend(
        [
            {
                "id": "link-expired",
                "session_id": SESSION_ID,
                "token_hash": "a" * 64,
                "expires_at": _past(),
                "redeemed_at": None,
            },
            {
                # Redeemed: evidence the vendor opened the session. Keep it.
                "id": "link-redeemed",
                "session_id": SESSION_ID,
                "token_hash": "b" * 64,
                "expires_at": _past(),
                "redeemed_at": _past(),
            },
            {
                "id": "link-live",
                "session_id": SESSION_ID,
                "token_hash": "c" * 64,
                "expires_at": _future(),
                "redeemed_at": None,
            },
        ]
    )

    body = client.post("/internal/intake/purge-links", headers=_headers()).json()
    assert body["deleted"] == 1

    remaining = {row["id"] for row in fake.table("intake_deep_links").rows}
    assert remaining == {"link-redeemed", "link-live"}


def test_link_sweep_is_idempotent(client: TestClient, fake: FakeSupabaseClient) -> None:
    fake.table("intake_deep_links").rows.append(
        {
            "id": "link-expired",
            "session_id": SESSION_ID,
            "token_hash": "a" * 64,
            "expires_at": _past(),
            "redeemed_at": None,
        }
    )
    client.post("/internal/intake/purge-links", headers=_headers())
    second = client.post("/internal/intake/purge-links", headers=_headers()).json()
    assert second["scanned"] == 0
    assert second["deleted"] == 0


# --- Metrics ----------------------------------------------------------------
def test_metrics_counts_every_disposition(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    _seed_sessions(fake)
    fake.table("intake_events").rows.extend(
        [
            {"kind": "ingestion", "disposition": "draft_created"},
            {"kind": "ingestion", "disposition": "draft_created"},
            {"kind": "ingestion", "disposition": "dropped_group"},
            # A transition row must not be counted as a disposition.
            {"kind": "transition", "to_status": "expired"},
        ]
    )

    body = client.get("/internal/intake/metrics", headers=_headers()).json()
    assert body["dispositions"]["draft_created"] == 2
    assert body["dispositions"]["dropped_group"] == 1
    assert body["dispositions"]["rejected_auth"] == 0
    assert body["session_statuses"]["approved"] == 1
    assert body["listings_created"] == 1


def test_metrics_reports_every_known_key_even_at_zero(
    client: TestClient, fake: FakeSupabaseClient
) -> None:
    """A digest that silently omits a zero row reads as 'not measured'."""
    _seed_sessions(fake)
    body = client.get("/internal/intake/metrics", headers=_headers()).json()
    assert set(body["dispositions"]) == set(state_machine.DISPOSITIONS)
    assert set(body["session_statuses"]) == set(state_machine.SESSION_STATUSES)


def test_metrics_does_not_mutate(client: TestClient, fake: FakeSupabaseClient) -> None:
    _seed_sessions(fake)
    before = [dict(row) for row in fake.table("intake_sessions").rows]
    client.get("/internal/intake/metrics", headers=_headers())
    assert fake.table("intake_sessions").rows == before


# --- Boundary properties ----------------------------------------------------
def test_module_has_no_outbound_path() -> None:
    """The ops lane sends nothing: no HTTP client, no outbox enqueue.

    Checked structurally rather than by grepping prose, so a comment mentioning
    httpx cannot pass and a real import cannot slip through.
    """
    source = Path(__file__).resolve().parents[1] / "app" / "routers" / "internal_intake.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            if node.module.startswith("app.services.notifications"):
                pytest.fail("internal_intake must not import the notification outbox")

    assert "httpx" not in imported
    assert "requests" not in imported

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "enqueue_outbox_row" not in called


def test_sweeps_never_touch_vendor_listings() -> None:
    """Operations may expire and minimise; they may never publish or unpublish."""
    source = Path(__file__).resolve().parents[1] / "app" / "routers" / "internal_intake.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    touched = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "vendor_listings" not in touched


def test_workflows_ship_inactive_and_carry_no_secret() -> None:
    """An imported workflow must not start running, and must not embed a token."""
    import json

    n8n_dir = Path(__file__).resolve().parents[3] / "infra" / "n8n"
    for name in ("waha-intake-sweeps.json", "waha-intake-digest.json"):
        data = json.loads((n8n_dir / name).read_text(encoding="utf-8"))
        assert data["active"] is False, f"{name} must ship inactive"

        raw = (n8n_dir / name).read_text(encoding="utf-8")
        # Tokens are referenced through $env, never inlined.
        assert "INTERNAL_INTAKE_TOKEN" in raw
        assert "dev-internal-intake" not in raw
