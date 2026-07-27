"""M18-P04 — inbound-only session progression (D35).

The defining assertion in this file is a negative one: the orchestrator sends
**nothing**. Follow-ups exist only as structured data on the intake record.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.services.intake import orchestrator, state_machine

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SESSION_A = "22222222-2222-4222-8222-222222222222"
SESSION_B = "33333333-3333-4333-8333-333333333333"

COMPLETE = "Samsung Fridge K3,500 brand new"


class FakeQuery:
    def __init__(self, t: FakeTable) -> None:
        self._t = t
        self._f: list[tuple[str, Any]] = []
        self._single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _c: str = "*", **_k: Any) -> FakeQuery:
        return self

    def eq(self, c: str, v: Any) -> FakeQuery:
        self._f.append((c, v))
        return self

    def in_(self, c: str, vals: list[Any]) -> FakeQuery:
        self._f.append((c, vals))
        return self

    def order(self, _c: str, **_k: Any) -> FakeQuery:
        return self

    def maybe_single(self) -> FakeQuery:
        self._single = True
        return self

    def insert(self, p: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = p
        return self

    def update(self, p: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = p
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for col, val in self._f:
            if isinstance(val, list):
                if row.get(col) not in val:
                    return False
            elif row.get(col) != val:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"{self._t.name}-{len(self._t.rows) + 1}")
            self._t.rows.append(row)
            return MagicMock(data=[dict(row)])
        if self._op == "update":
            assert self._payload is not None
            changed = []
            for row in self._t.rows:
                if self._match(row):
                    row.update(self._payload)
                    changed.append(dict(row))
            return MagicMock(data=changed)
        rows = [dict(r) for r in self._t.rows if self._match(r)]
        if self._single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, c: str = "*", **k: Any) -> FakeQuery:
        return FakeQuery(self).select(c, **k)

    def insert(self, p: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(p)

    def update(self, p: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(p)


class FakeDB:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


class Wrapper:
    def __init__(self) -> None:
        self.client = FakeDB()

    def rows(self, n: str) -> list[dict[str, Any]]:
        return self.client.table(n).rows


@pytest.fixture()
def store() -> Wrapper:
    w = Wrapper()
    w.rows("intake_sessions").append(
        {
            "id": SESSION_A,
            "vendor_id": VENDOR_A,
            "status": state_machine.COLLECTING,
            "pending_requests": [],
        }
    )
    return w


def _progress(store: Wrapper, text: str | None, **kw: Any) -> dict[str, Any]:
    return orchestrator.progress_session(
        store, session_id=SESSION_A, vendor_id=VENDOR_A, text=text, **kw
    )


def _questions(store: Wrapper) -> list[dict[str, Any]]:
    return store.rows("intake_sessions")[0].get("pending_requests") or []


# ---------------------------------------------------------------------------
# The defining property: zero outbound
# ---------------------------------------------------------------------------
def test_orchestrator_imports_no_outbound_capability() -> None:
    """Strictly inbound-only: no HTTP client, no outbox, no notification path."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(orchestrator))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    for forbidden in ("httpx", "requests", "aiohttp"):
        assert forbidden not in imported, f"outbound capability leaked: {forbidden}"

    # Strip docstrings so the prose explaining the rule doesn't trip the check.
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                node.value.value = ""
    code = ast.unparse(tree)
    for forbidden in ("enqueue_outbox_row", "notification_outbox", "send_message"):
        assert forbidden not in code, f"outbound capability leaked: {forbidden}"


def test_no_outbox_row_is_ever_written(store: Wrapper) -> None:
    _progress(store, "Fridge K3500")
    assert store.rows("notification_outbox") == []


def test_follow_ups_are_data_not_messages(store: Wrapper) -> None:
    """A missing field produces a row on the record, not a send."""
    _progress(store, "Fridge K3500", has_media=True)
    questions = _questions(store)
    assert questions, "expected recorded follow-ups"
    for q in questions:
        assert q["key"].startswith("intake.question.")
        # i18n keys + params only — no user-facing copy in the API.
        assert set(q).issubset({"key", "field_name", "params"})
    assert store.rows("notification_outbox") == []


# ---------------------------------------------------------------------------
# Progression
# ---------------------------------------------------------------------------
def test_incomplete_draft_goes_to_needs_details(store: Wrapper) -> None:
    _progress(store, "Fridge", has_media=True)
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS
    keys = [q["key"] for q in _questions(store)]
    assert "intake.question.price_missing" in keys


def test_complete_draft_becomes_ready_for_vendor_review(store: Wrapper) -> None:
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    assert (
        store.rows("intake_sessions")[0]["status"]
        == state_machine.READY_FOR_VENDOR_REVIEW
    )
    assert _questions(store) == []


def test_missing_photo_blocks_readiness(store: Wrapper) -> None:
    _progress(store, COMPLETE, category_slug="appliances", has_media=False)
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS
    assert "intake.question.photo_missing" in [q["key"] for q in _questions(store)]


def test_orchestrator_never_reaches_submitted(store: Wrapper) -> None:
    """Submission is the vendor's explicit act in M18-P05, never automatic."""
    for _ in range(3):
        _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    status = store.rows("intake_sessions")[0]["status"]
    assert status == state_machine.READY_FOR_VENDOR_REVIEW
    assert status not in {
        state_machine.SUBMITTED,
        state_machine.PENDING_ADMIN_REVIEW,
        state_machine.APPROVED,
    }


def test_terminal_session_is_left_alone(store: Wrapper) -> None:
    store.rows("intake_sessions")[0]["status"] = state_machine.APPROVED
    result = _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    assert result["status"] == state_machine.APPROVED


def test_repeated_progress_is_stable(store: Wrapper) -> None:
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    first = dict(store.rows("intake_sessions")[0])
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    assert store.rows("intake_sessions")[0]["status"] == first["status"]
    assert len(store.rows("intake_draft_fields")) == 1, "draft upserted, not duplicated"


# ---------------------------------------------------------------------------
# Contradictions and prohibited classes
# ---------------------------------------------------------------------------
def test_contradictory_price_is_surfaced_not_resolved(store: Wrapper) -> None:
    _progress(store, "Fridge was K5000 now K3500 brand new", category_slug="appliances",
              has_media=True)
    keys = [q["key"] for q in _questions(store)]
    assert "intake.question.price_conflict" in keys
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS


def test_prohibited_class_cannot_advance(store: Wrapper) -> None:
    _progress(store, "Cement bags K90 new", category_slug="cement", has_media=True)
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS
    keys = [q["key"] for q in _questions(store)]
    assert "intake.question.prohibited_class" in keys


# ---------------------------------------------------------------------------
# Duplicates are flagged, never merged or rejected
# ---------------------------------------------------------------------------
def test_near_identical_draft_is_flagged_for_review(store: Wrapper) -> None:
    from app.services.intake import extract

    # Seed the earlier draft with what the extractor actually derives from the
    # same message, rather than a hand-written guess at the title.
    store.rows("intake_draft_fields").append(
        {
            "session_id": SESSION_B,
            "title": extract.derive_title(COMPLETE),
            "price_ngwee": extract.parse_price_ngwee(COMPLETE),
        }
    )
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)

    keys = [q["key"] for q in _questions(store)]
    assert "intake.question.possible_duplicate" in keys
    # Flagged, not auto-merged: the earlier draft is untouched...
    assert any(r["session_id"] == SESSION_B for r in store.rows("intake_draft_fields"))
    # ...and not auto-rejected.
    assert store.rows("intake_sessions")[0]["status"] != state_machine.REJECTED


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------
def test_rule_derived_fields_are_labelled(store: Wrapper) -> None:
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    sources = {r["source"] for r in store.rows("intake_field_provenance")}
    assert sources == {"rule"}


def test_model_fields_are_labelled_and_additive(store: Wrapper) -> None:
    _progress(
        store,
        "Fridge K3500",
        category_slug="appliances",
        has_media=True,
        model_payload={"condition": "new"},
        model_ref="test-model",
        model_confidence=0.7,
    )
    by_field = {r["field_name"]: r for r in store.rows("intake_field_provenance")}
    assert by_field["condition"]["source"] == "model"
    assert by_field["condition"]["model_ref"] == "test-model"
    assert by_field["price_ngwee"]["source"] == "rule"


def test_vendor_correction_is_never_downgraded(store: Wrapper) -> None:
    """A later inbound message must not relabel a vendor's own edit."""
    store.rows("intake_field_provenance").append(
        {"session_id": SESSION_A, "field_name": "title", "source": "vendor_typed"}
    )
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    title_rows = [
        r
        for r in store.rows("intake_field_provenance")
        if r["field_name"] == "title" and r["session_id"] == SESSION_A
    ]
    assert all(r["source"] == "vendor_typed" for r in title_rows)


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------
def test_no_model_still_progresses(store: Wrapper) -> None:
    """AI unavailable / over quota / kill-switched ⇒ rules-only, still works."""
    _progress(store, COMPLETE, category_slug="appliances", has_media=True, model_payload=None)
    assert (
        store.rows("intake_sessions")[0]["status"]
        == state_machine.READY_FOR_VENDOR_REVIEW
    )
    assert {r["source"] for r in store.rows("intake_field_provenance")} == {"rule"}


def test_invalid_model_output_does_not_block_progress(store: Wrapper) -> None:
    _progress(
        store,
        COMPLETE,
        category_slug="appliances",
        has_media=True,
        model_payload={"price_ngwee": "free"},
        model_ref="bad",
    )
    assert (
        store.rows("intake_sessions")[0]["status"]
        == state_machine.READY_FOR_VENDOR_REVIEW
    )
    assert store.rows("intake_draft_fields")[0]["price_ngwee"] == 350_000


def test_empty_text_is_handled(store: Wrapper) -> None:
    _progress(store, None, has_media=False)
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS


def test_draft_never_writes_vendor_listings(store: Wrapper) -> None:
    _progress(store, COMPLETE, category_slug="appliances", has_media=True)
    assert "vendor_listings" not in store.client.tables
