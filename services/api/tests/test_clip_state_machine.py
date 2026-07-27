"""M17-P01 — guarded clip lifecycle.

The properties worth defending here are the ones a later pebble will lean on
without re-checking:

* only the moves in the allow-map exist, and everything else raises;
* two concurrent transitions produce exactly one winner and one 409, because the
  from-state is asserted **inside** the UPDATE rather than read first;
* leaving ``published`` is what makes takedown instant-hide — the RLS policy in
  0076 matches that status and nothing else;
* counters move only through the ``SECURITY DEFINER`` RPC, never a table UPDATE.
"""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.clips import state_machine

CLIP_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
VENDOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ADMIN_ID = "11111111-1111-4111-8111-111111111111"


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
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
        return all(row.get(column) == value for column, value in self._filters)

    def execute(self) -> MagicMock:
        with self._parent.lock:
            if self._op == "insert":
                assert self._payload is not None
                row = dict(self._payload)
                row.setdefault("id", f"{self._parent.name}-{len(self._parent.rows)}")
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

            rows = [dict(row) for row in self._parent.rows if self._match(row)]
            if self._maybe_single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def select(self, columns: str = "*", **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.counters: dict[tuple[str, str], int] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        self.rpc_calls.append((name, dict(params)))
        key = (str(params.get("p_clip_id")), str(params.get("p_column")))
        self.counters[key] = max(0, self.counters.get(key, 0) + int(params.get("p_delta", 0)))
        return MagicMock(execute=lambda: MagicMock(data=self.counters[key]))


class Store:
    def __init__(self) -> None:
        self.client = FakeSupabase()

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows


@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("video_clips").append(
        {
            "id": CLIP_ID,
            "vendor_id": VENDOR_ID,
            "status": state_machine.DRAFT,
            "published_at": None,
            "taken_down_at": None,
            "rejection_reason": None,
            "like_count": 0,
            "comment_count": 0,
            "view_count": 0,
        }
    )
    st.rows("audit_log")
    return st


def _set_status(store: Store, status: str) -> None:
    store.rows("video_clips")[0]["status"] = status


# --- Legal transitions ------------------------------------------------------
@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (state_machine.DRAFT, state_machine.SCREENING),
        (state_machine.SCREENING, state_machine.PENDING_REVIEW),
        (state_machine.SCREENING, state_machine.REJECTED),
        (state_machine.PENDING_REVIEW, state_machine.PUBLISHED),
        (state_machine.PENDING_REVIEW, state_machine.REJECTED),
        (state_machine.PUBLISHED, state_machine.TAKEN_DOWN),
    ],
)
def test_every_legal_transition_is_allowed(
    store: Store, from_status: str, to_status: str
) -> None:
    _set_status(store, from_status)
    updated = state_machine.transition(store, clip_id=CLIP_ID, to_status=to_status)
    assert updated["status"] == to_status


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        # Skipping the screen entirely — the whole point of D-V8.
        (state_machine.DRAFT, state_machine.PUBLISHED),
        (state_machine.DRAFT, state_machine.PENDING_REVIEW),
        (state_machine.SCREENING, state_machine.PUBLISHED),
        # Backwards moves.
        (state_machine.PENDING_REVIEW, state_machine.DRAFT),
        (state_machine.PUBLISHED, state_machine.PENDING_REVIEW),
        # Terminal states are terminal.
        (state_machine.REJECTED, state_machine.PUBLISHED),
        (state_machine.REJECTED, state_machine.DRAFT),
        (state_machine.TAKEN_DOWN, state_machine.PUBLISHED),
        # Takedown only means "was public"; an unpublished clip is rejected instead.
        (state_machine.DRAFT, state_machine.TAKEN_DOWN),
        (state_machine.PENDING_REVIEW, state_machine.TAKEN_DOWN),
    ],
)
def test_every_illegal_transition_is_rejected(
    store: Store, from_status: str, to_status: str
) -> None:
    _set_status(store, from_status)
    with pytest.raises(AppError) as exc:
        state_machine.transition(store, clip_id=CLIP_ID, to_status=to_status)
    assert exc.value.code == "clip_invalid_transition"
    assert exc.value.http_status == 409
    # And the row did not move.
    assert store.rows("video_clips")[0]["status"] == from_status


def test_a_draft_can_never_reach_published_in_one_step(store: Store) -> None:
    """The automated screen and the human queue are not optional (D-V8)."""
    assert state_machine.PUBLISHED not in state_machine.ALLOWED_TRANSITIONS[
        state_machine.DRAFT
    ]
    assert state_machine.PUBLISHED not in state_machine.ALLOWED_TRANSITIONS[
        state_machine.SCREENING
    ]
    # The ONLY predecessor of published is pending_review.
    predecessors = [
        source
        for source, targets in state_machine.ALLOWED_TRANSITIONS.items()
        if state_machine.PUBLISHED in targets
    ]
    assert predecessors == [state_machine.PENDING_REVIEW]


# --- Concurrency ------------------------------------------------------------
def test_concurrent_transition_has_exactly_one_winner(store: Store) -> None:
    """Two reviewers approving at once: one wins, the other gets a 409."""
    _set_status(store, state_machine.PENDING_REVIEW)

    def publish() -> str | None:
        try:
            state_machine.publish(store, clip_id=CLIP_ID, actor_id=ADMIN_ID)
            return "won"
        except AppError as exc:
            assert exc.code in {"clip_transition_conflict", "clip_invalid_transition"}
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(publish), pool.submit(publish)]]

    assert results.count("won") == 1
    assert store.rows("video_clips")[0]["status"] == state_machine.PUBLISHED


def test_a_stale_from_state_is_a_conflict_not_an_overwrite(store: Store) -> None:
    """The from-state lives in the WHERE clause, so a loser cannot clobber."""
    _set_status(store, state_machine.PENDING_REVIEW)
    state_machine.publish(store, clip_id=CLIP_ID)

    # A second caller that still believes the clip is pending_review.
    with pytest.raises(AppError) as exc:
        state_machine.transition(
            store, clip_id=CLIP_ID, to_status=state_machine.REJECTED, reason="too late"
        )
    assert exc.value.code == "clip_invalid_transition"
    assert store.rows("video_clips")[0]["status"] == state_machine.PUBLISHED
    assert store.rows("video_clips")[0]["rejection_reason"] is None


# --- Visibility -------------------------------------------------------------
def test_takedown_leaves_the_only_publicly_visible_status(store: Store) -> None:
    """Instant-hide: the RLS policy matches `published`, so leaving it hides."""
    _set_status(store, state_machine.PUBLISHED)
    assert state_machine.is_public(store.rows("video_clips")[0]["status"])

    updated = state_machine.take_down(store, clip_id=CLIP_ID, actor_id=ADMIN_ID)

    assert updated["status"] == state_machine.TAKEN_DOWN
    assert not state_machine.is_public(updated["status"])
    assert updated["taken_down_at"] is not None


def test_only_published_is_public(store: Store) -> None:
    for status in state_machine.CLIP_STATUSES:
        assert state_machine.is_public(status) == (status == state_machine.PUBLISHED)


def test_publish_stamps_published_at(store: Store) -> None:
    _set_status(store, state_machine.PENDING_REVIEW)
    updated = state_machine.publish(store, clip_id=CLIP_ID)
    assert updated["published_at"] is not None


def test_reject_records_the_reason(store: Store) -> None:
    _set_status(store, state_machine.PENDING_REVIEW)
    updated = state_machine.reject(store, clip_id=CLIP_ID, reason="prohibited category")
    assert updated["rejection_reason"] == "prohibited category"


# --- Audit ------------------------------------------------------------------
def test_every_transition_writes_one_audit_row(store: Store) -> None:
    _set_status(store, state_machine.DRAFT)
    state_machine.start_screening(store, clip_id=CLIP_ID)
    state_machine.pass_screening(store, clip_id=CLIP_ID)
    state_machine.publish(store, clip_id=CLIP_ID, actor_id=ADMIN_ID)

    audit = store.rows("audit_log")
    assert len(audit) == 3
    assert [row["after"]["status"] for row in audit] == [
        state_machine.SCREENING,
        state_machine.PENDING_REVIEW,
        state_machine.PUBLISHED,
    ]
    assert all(row["entity_type"] == "video_clip" for row in audit)
    assert all(row["entity_id"] == CLIP_ID for row in audit)
    assert audit[-1]["actor"] == ADMIN_ID
    assert audit[-1]["before"]["status"] == state_machine.PENDING_REVIEW


def test_a_refused_transition_writes_no_audit_row(store: Store) -> None:
    _set_status(store, state_machine.DRAFT)
    with pytest.raises(AppError):
        state_machine.transition(
            store, clip_id=CLIP_ID, to_status=state_machine.PUBLISHED
        )
    assert store.rows("audit_log") == []


# --- Vendor suspension cascade ----------------------------------------------
def test_vendor_suspension_takes_down_every_published_clip(store: Store) -> None:
    _set_status(store, state_machine.PUBLISHED)
    store.rows("video_clips").extend(
        [
            {
                "id": "clip-2",
                "vendor_id": VENDOR_ID,
                "status": state_machine.PUBLISHED,
                "published_at": "2026-07-01T00:00:00+00:00",
                "taken_down_at": None,
                "rejection_reason": None,
            },
            {
                # A draft is already invisible; the cascade must not touch it.
                "id": "clip-3",
                "vendor_id": VENDOR_ID,
                "status": state_machine.DRAFT,
                "published_at": None,
                "taken_down_at": None,
                "rejection_reason": None,
            },
        ]
    )

    taken = state_machine.take_down_vendor_clips(
        store, vendor_id=VENDOR_ID, actor_id=ADMIN_ID
    )

    assert sorted(taken) == sorted([CLIP_ID, "clip-2"])
    by_id = {row["id"]: row for row in store.rows("video_clips")}
    assert by_id[CLIP_ID]["status"] == state_machine.TAKEN_DOWN
    assert by_id["clip-2"]["status"] == state_machine.TAKEN_DOWN
    assert by_id["clip-3"]["status"] == state_machine.DRAFT


# --- Counters ---------------------------------------------------------------
def test_counters_move_only_through_the_definer_function(store: Store) -> None:
    """No table UPDATE — the RPC is the only path with the privilege."""
    value = state_machine.bump_counter(
        store, clip_id=CLIP_ID, column=state_machine.LIKE_COUNT, delta=1
    )
    assert value == 1
    assert store.client.rpc_calls == [
        (
            "clip_bump_counter",
            {"p_clip_id": CLIP_ID, "p_column": "like_count", "p_delta": 1},
        )
    ]
    # The row itself was never UPDATEd by the application.
    assert store.rows("video_clips")[0]["like_count"] == 0


def test_counter_bumps_are_relative_so_concurrency_cannot_lose_one(store: Store) -> None:
    for _ in range(5):
        state_machine.bump_counter(
            store, clip_id=CLIP_ID, column=state_machine.VIEW_COUNT, delta=1
        )
    assert store.client.counters[(CLIP_ID, "view_count")] == 5
    # Every call passed a delta, never an absolute value.
    assert all(call[1]["p_delta"] == 1 for call in store.client.rpc_calls)


def test_counter_cannot_go_negative(store: Store) -> None:
    state_machine.bump_counter(
        store, clip_id=CLIP_ID, column=state_machine.LIKE_COUNT, delta=1
    )
    state_machine.bump_counter(
        store, clip_id=CLIP_ID, column=state_machine.LIKE_COUNT, delta=-1
    )
    state_machine.bump_counter(
        store, clip_id=CLIP_ID, column=state_machine.LIKE_COUNT, delta=-1
    )
    assert store.client.counters[(CLIP_ID, "like_count")] == 0


def test_an_unknown_counter_is_refused(store: Store) -> None:
    with pytest.raises(AppError) as exc:
        state_machine.bump_counter(
            store, clip_id=CLIP_ID, column="vendor_id", delta=1
        )
    assert exc.value.code == "clip_invalid_counter"
    assert store.client.rpc_calls == []


# --- Misc -------------------------------------------------------------------
def test_unknown_clip_is_404(store: Store) -> None:
    with pytest.raises(AppError) as exc:
        state_machine.transition(
            store, clip_id="00000000-0000-0000-0000-000000000000",
            to_status=state_machine.SCREENING,
        )
    assert exc.value.http_status == 404


def test_unknown_target_status_is_refused(store: Store) -> None:
    with pytest.raises(AppError) as exc:
        state_machine.transition(store, clip_id=CLIP_ID, to_status="promoted")
    assert exc.value.code == "clip_invalid_status"


def test_terminal_states_have_no_outgoing_moves() -> None:
    for status in state_machine.TERMINAL_STATUSES:
        assert state_machine.ALLOWED_TRANSITIONS[status] == frozenset()
        assert state_machine.is_terminal(status)
