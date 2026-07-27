"""M18-P01 — guarded intake state machine + session service (D35).

The properties under test are the ones that make the lane safe:
illegal moves are impossible, concurrent moves cannot both win, replays are
no-ops, and an ineligible sender learns nothing about whether an account exists.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.intake import sessions, state_machine

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
BINDING_A = "11111111-1111-4111-8111-111111111111"
SESSION_A = "22222222-2222-4222-8222-222222222222"
MSISDN_A = "260971234567"


# ---------------------------------------------------------------------------
# In-memory Supabase double with a lock, so the concurrency test is real.
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, table: FakeTable) -> None:
        self._t = table
        self._filters: list[tuple[str, Any]] = []
        self._in: tuple[str, list[Any]] | None = None
        self._is_null: list[str] = []
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _c: str = "*", **_k: Any) -> FakeQuery:
        return self

    def eq(self, col: str, val: Any) -> FakeQuery:
        self._filters.append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> FakeQuery:
        self._in = (col, vals)
        return self

    def is_(self, col: str, _val: Any) -> FakeQuery:
        self._is_null.append(col)
        return self

    def order(self, _c: str, **_k: Any) -> FakeQuery:
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

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._filters):
            return False
        if self._in is not None:
            col, vals = self._in
            if row.get(col) not in vals:
                return False
        return all(row.get(c) is None for c in self._is_null)

    def execute(self) -> MagicMock:
        with self._t.db.lock:
            if self._op == "insert":
                assert self._payload is not None
                row = dict(self._payload)
                row.setdefault("id", f"{self._t.name}-{len(self._t.rows) + 1}")
                self._t.check(row)
                self._t.rows.append(row)
                return MagicMock(data=[dict(row)])

            if self._op == "update":
                assert self._payload is not None
                changed: list[dict[str, Any]] = []
                for row in self._t.rows:
                    if self._match(row):
                        row.update(self._payload)
                        changed.append(dict(row))
                return MagicMock(data=changed)

            rows = [dict(r) for r in self._t.rows if self._match(r)]
            if self._maybe_single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)


class FakeTable:
    def __init__(self, db: FakeDB, name: str) -> None:
        self.db = db
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def check(self, row: dict[str, Any]) -> None:
        """Enforce the DB constraints the tests rely on."""
        if self.name == "intake_messages":
            pid = row.get("provider_message_id")
            if any(r.get("provider_message_id") == pid for r in self.rows):
                raise RuntimeError("duplicate key value violates unique constraint")
        if self.name == "intake_events":
            # Mirrors intake_events_shape_ck.
            kind = row.get("kind")
            if kind == "ingestion":
                assert row.get("disposition") is not None
                assert row.get("to_status") is None
            elif kind == "transition":
                assert row.get("session_id") is not None
                assert row.get("to_status") is not None
            else:  # pragma: no cover - guard
                raise AssertionError(f"bad event kind {kind!r}")

    def select(self, c: str = "*", **k: Any) -> FakeQuery:
        return FakeQuery(self).select(c, **k)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeDB:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable(self, name)
        return self.tables[name]


class FakeServiceClient:
    def __init__(self) -> None:
        self.client = FakeDB()

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.client.table(table).rows


@pytest.fixture()
def client() -> FakeServiceClient:
    sc = FakeServiceClient()
    sc.client.table("vendors").rows.append(
        {"id": VENDOR_A, "status": "active", "kyc_tier": 1}
    )
    sc.client.table("intake_vendor_bindings").rows.append(
        {"id": BINDING_A, "vendor_id": VENDOR_A, "msisdn": MSISDN_A, "opted_out_at": None}
    )
    return sc


def _session(client: FakeServiceClient, status: str, session_id: str = SESSION_A) -> None:
    client.client.table("intake_sessions").rows.append(
        {"id": session_id, "vendor_id": VENDOR_A, "binding_id": BINDING_A, "status": status}
    )


# ---------------------------------------------------------------------------
# Transitions: only the moves that exist
# ---------------------------------------------------------------------------
LEGAL = [
    ("collecting", "needs_details"),
    ("collecting", "ready_for_vendor_review"),
    ("collecting", "expired"),
    ("needs_details", "collecting"),
    ("needs_details", "ready_for_vendor_review"),
    ("ready_for_vendor_review", "submitted"),
    ("ready_for_vendor_review", "needs_details"),
    ("submitted", "pending_admin_review"),
    ("pending_admin_review", "approved"),
    ("pending_admin_review", "rejected"),
    ("pending_admin_review", "needs_details"),
]

ILLEGAL = [
    ("collecting", "submitted"),
    ("collecting", "approved"),
    ("collecting", "pending_admin_review"),
    ("needs_details", "approved"),
    ("ready_for_vendor_review", "approved"),
    ("ready_for_vendor_review", "pending_admin_review"),
    ("submitted", "approved"),
    ("submitted", "rejected"),
    ("approved", "rejected"),
    ("rejected", "approved"),
    ("expired", "collecting"),
    ("approved", "collecting"),
]


@pytest.mark.parametrize(("frm", "to"), LEGAL)
def test_legal_transition_succeeds(client: FakeServiceClient, frm: str, to: str) -> None:
    _session(client, frm)
    result = state_machine.transition(client, session_id=SESSION_A, to_status=to)
    assert result["status"] == to


@pytest.mark.parametrize(("frm", "to"), ILLEGAL)
def test_illegal_transition_rejected(client: FakeServiceClient, frm: str, to: str) -> None:
    _session(client, frm)
    with pytest.raises(AppError) as exc:
        state_machine.transition(client, session_id=SESSION_A, to_status=to)
    assert exc.value.code == "intake_invalid_transition"
    assert exc.value.http_status == 409
    # The row must be untouched.
    assert client.rows("intake_sessions")[0]["status"] == frm


def test_no_transition_out_of_a_terminal_state(client: FakeServiceClient) -> None:
    for terminal in ("approved", "rejected", "expired"):
        assert state_machine.ALLOWED_TRANSITIONS[terminal] == frozenset()
        assert state_machine.is_terminal(terminal)


@pytest.mark.parametrize(
    "frm",
    [
        "collecting",
        "needs_details",
        "ready_for_vendor_review",
        "submitted",
        "pending_admin_review",
    ],
)
def test_expire_reachable_from_every_non_terminal_state(
    client: FakeServiceClient, frm: str
) -> None:
    _session(client, frm)
    assert state_machine.expire(client, session_id=SESSION_A)["status"] == "expired"


def test_unknown_target_status_raises(client: FakeServiceClient) -> None:
    _session(client, "collecting")
    with pytest.raises(AppError) as exc:
        state_machine.transition(client, session_id=SESSION_A, to_status="nonsense")
    assert exc.value.code == "intake_invalid_status"


def test_missing_session_raises_404(client: FakeServiceClient) -> None:
    with pytest.raises(AppError) as exc:
        state_machine.transition(client, session_id="nope", to_status="expired")
    assert exc.value.http_status == 404


# ---------------------------------------------------------------------------
# Concurrency: two writers, one winner
# ---------------------------------------------------------------------------
def test_concurrent_transition_one_wins_other_409(client: FakeServiceClient) -> None:
    _session(client, "pending_admin_review")

    results: list[str] = []
    errors: list[AppError] = []

    def go(target: str) -> None:
        try:
            state_machine.transition(client, session_id=SESSION_A, to_status=target)
            results.append(target)
        except AppError as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(go, ["approved", "rejected"]))

    assert len(results) == 1, "exactly one transition must win"
    assert len(errors) == 1
    assert errors[0].http_status == 409
    assert errors[0].code in {"intake_transition_conflict", "intake_invalid_transition"}


def test_transition_writes_an_audit_row(client: FakeServiceClient) -> None:
    _session(client, "collecting")
    state_machine.transition(client, session_id=SESSION_A, to_status="needs_details")
    events = client.rows("intake_events")
    assert len(events) == 1
    assert events[0]["kind"] == "transition"
    assert events[0]["from_status"] == "collecting"
    assert events[0]["to_status"] == "needs_details"
    # A state change carries no ingestion disposition.
    assert events[0].get("disposition") is None


def test_rejection_reason_is_persisted(client: FakeServiceClient) -> None:
    _session(client, "pending_admin_review")
    state_machine.transition(
        client, session_id=SESSION_A, to_status="rejected", reason="prohibited category"
    )
    assert client.rows("intake_sessions")[0]["rejection_reason"] == "prohibited category"


def test_ingestion_event_requires_a_known_disposition(client: FakeServiceClient) -> None:
    with pytest.raises(AppError) as exc:
        state_machine.record_ingestion(client, disposition="made_up")
    assert exc.value.code == "invalid_intake_disposition"


def test_disposition_taxonomy_is_exactly_d35() -> None:
    assert state_machine.DISPOSITIONS == frozenset(
        {
            "draft_created",
            "dropped_group",
            "dropped_unverified",
            "dropped_flag_off",
            "rejected_auth",
            "error",
        }
    )


# ---------------------------------------------------------------------------
# No account disclosure — the property that keeps the number un-probeable
# ---------------------------------------------------------------------------
def test_unknown_number_is_not_eligible(client: FakeServiceClient) -> None:
    assert sessions.resolve_verified_sender(client, "260979999999") is None


def test_suspended_vendor_is_not_eligible(client: FakeServiceClient) -> None:
    client.rows("vendors")[0]["status"] = "suspended"
    assert sessions.resolve_verified_sender(client, MSISDN_A) is None


def test_under_tier_vendor_is_not_eligible(client: FakeServiceClient) -> None:
    client.rows("vendors")[0]["kyc_tier"] = 0
    assert sessions.resolve_verified_sender(client, MSISDN_A) is None


def test_opted_out_binding_is_not_eligible(client: FakeServiceClient) -> None:
    client.rows("intake_vendor_bindings")[0]["opted_out_at"] = "2026-07-01T00:00:00Z"
    assert sessions.resolve_verified_sender(client, MSISDN_A) is None


def test_ineligible_outcomes_are_indistinguishable(
    client: FakeServiceClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Unknown vs suspended vs under-tier must produce the same value AND log.

    If these differed, the intake number would become an oracle for "is this
    business on Vergeo5, and what is its status" — answerable by anyone who can
    send a WhatsApp message.
    """
    messages: list[list[str]] = []
    for mutate in (
        lambda: None,
        lambda: client.rows("vendors")[0].update({"status": "suspended"}),
        lambda: client.rows("vendors")[0].update({"status": "active", "kyc_tier": 0}),
    ):
        mutate()
        caplog.clear()
        with caplog.at_level("INFO"):
            unknown = sessions.resolve_verified_sender(client, "260979999999")
            known = sessions.resolve_verified_sender(client, MSISDN_A)
        assert unknown is None
        if known is None:
            messages.append([r.getMessage() for r in caplog.records])

    assert messages, "expected at least one ineligible scenario"
    for group in messages:
        assert set(group) == {"intake sender not eligible"}


def test_no_vendor_identifier_leaks_on_rejection(
    client: FakeServiceClient, caplog: pytest.LogCaptureFixture
) -> None:
    client.rows("vendors")[0]["status"] = "suspended"
    with caplog.at_level("INFO"):
        assert sessions.resolve_verified_sender(client, MSISDN_A) is None
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert VENDOR_A not in blob
    assert MSISDN_A not in blob


def test_eligible_sender_resolves(client: FakeServiceClient) -> None:
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None
    assert sender.vendor_id == VENDOR_A
    assert sender.binding_id == BINDING_A


def test_db_error_fails_closed(client: FakeServiceClient) -> None:
    class Boom:
        client = MagicMock()

        def __init__(self) -> None:
            self.client.table.side_effect = RuntimeError("down")

    assert sessions.resolve_verified_sender(Boom(), MSISDN_A) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("260971234567", "260971234567"),
        ("+260 97 123 4567", "260971234567"),
        ("0971234567", "260971234567"),
        ("260961234567", "260961234567"),  # 260 + 9 + 8 digits is valid
        ("260861234567", None),  # prefix digit must be 7 or 9
        ("26097123456", None),  # too short
        ("2609712345678", None),  # too long
        ("", None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_msisdn_normalisation(raw: str | None, expected: str | None) -> None:
    assert sessions.normalise_msisdn(raw) == expected


# ---------------------------------------------------------------------------
# Idempotency: a replayed message changes nothing
# ---------------------------------------------------------------------------
def test_replayed_message_is_a_no_op(client: FakeServiceClient) -> None:
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None

    first = sessions.record_inbound(client, sender=sender, provider_message_id="wamid.1")
    second = sessions.record_inbound(client, sender=sender, provider_message_id="wamid.1")

    assert first["id"] == second["id"]
    assert len(client.rows("intake_sessions")) == 1, "no second session"
    assert len(client.rows("intake_messages")) == 1, "no second message row"
    ingestions = [e for e in client.rows("intake_events") if e["kind"] == "ingestion"]
    assert len(ingestions) == 1, "no second audit row"


def test_second_distinct_message_joins_the_same_open_session(
    client: FakeServiceClient,
) -> None:
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None
    a = sessions.record_inbound(client, sender=sender, provider_message_id="wamid.1")
    b = sessions.record_inbound(client, sender=sender, provider_message_id="wamid.2")
    assert a["id"] == b["id"]
    assert len(client.rows("intake_messages")) == 2


def test_inbound_records_ingestion_disposition(client: FakeServiceClient) -> None:
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None
    sessions.record_inbound(client, sender=sender, provider_message_id="wamid.1")
    event = client.rows("intake_events")[0]
    assert event["kind"] == "ingestion"
    assert event["disposition"] == "draft_created"


def test_unknown_message_kind_is_downgraded(client: FakeServiceClient) -> None:
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None
    sessions.record_inbound(
        client, sender=sender, provider_message_id="wamid.9", kind="video"
    )
    assert client.rows("intake_messages")[0]["kind"] == "unsupported"


def test_raw_excerpt_is_stored_for_purge(client: FakeServiceClient) -> None:
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None
    sessions.record_inbound(
        client, sender=sender, provider_message_id="wamid.1", raw_excerpt="Fridge K3500"
    )
    row = client.rows("intake_messages")[0]
    assert row["raw_excerpt"] == "Fridge K3500"


# ---------------------------------------------------------------------------
# Enrollment is reversible
# ---------------------------------------------------------------------------
def test_disenroll_then_reenroll(client: FakeServiceClient) -> None:
    sessions.disenroll(client, binding_id=BINDING_A)
    assert sessions.resolve_verified_sender(client, MSISDN_A) is None
    # The row is retained for audit, not deleted.
    assert len(client.rows("intake_vendor_bindings")) == 1
    assert client.rows("intake_vendor_bindings")[0]["opted_out_at"] is not None

    sessions.enroll(client, vendor_id=VENDOR_A, raw_msisdn=MSISDN_A)
    assert sessions.resolve_verified_sender(client, MSISDN_A) is not None


def test_enroll_rejects_a_non_zambian_mobile(client: FakeServiceClient) -> None:
    with pytest.raises(AppError) as exc:
        sessions.enroll(client, vendor_id=VENDOR_A, raw_msisdn="+44 7700 900000")
    assert exc.value.code == "invalid_msisdn"


def test_ambiguous_binding_is_not_eligible(client: FakeServiceClient) -> None:
    """The unique partial index makes this impossible; if it happens, refuse."""
    client.rows("intake_vendor_bindings").append(
        {"id": "dup", "vendor_id": VENDOR_B, "msisdn": MSISDN_A, "opted_out_at": None}
    )
    assert sessions.resolve_verified_sender(client, MSISDN_A) is None


# ---------------------------------------------------------------------------
# Boundary
# ---------------------------------------------------------------------------
def test_modules_expose_no_send_capability() -> None:
    """D35 is strictly inbound-only: nothing here may acquire a sender."""
    for module in (sessions, state_machine):
        exported = dir(module)
        for forbidden in ("send", "send_message", "post_message", "ack", "reply", "notify"):
            assert forbidden not in exported


def test_nothing_here_queries_vendor_listings(client: FakeServiceClient) -> None:
    """Only M18-P05 may hand an intake record into the listing flow.

    Asserted behaviourally: drive the full inbound + transition path and check
    that ``vendor_listings`` was never among the tables touched.
    """
    sender = sessions.resolve_verified_sender(client, MSISDN_A)
    assert sender is not None
    sessions.record_inbound(client, sender=sender, provider_message_id="wamid.1")
    state_machine.transition(
        client, session_id=client.rows("intake_sessions")[0]["id"],
        to_status="ready_for_vendor_review",
    )
    assert "vendor_listings" not in client.client.tables
