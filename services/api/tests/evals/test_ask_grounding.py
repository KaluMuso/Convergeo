"""Ask Vergeo grounding eval gate (M06-P05).

Drives the real ``run_ask`` pipeline against a static, version-controlled eval
set (``ask_eval_set.yaml``). Retrieval and the model call are injected, so the
whole suite is deterministic and needs no live API key in CI:

* a fixture retriever returns each entry's ``fixture_docs``;
* a recorded ``model_caller`` returns each entry's ``recorded_answer``.

Grounding invariants asserted per question:
  1. no cited ``entity_id`` outside the retrieved fixture set (no fabrication);
  2. ``refused`` matches expectation (trap / no-answer questions refuse);
  3. ZMW ngwee -> decimal is correct in the citation ``price_display``.

Local live mode: set ``ASK_EVAL_LIVE=1`` (the ``--ask-live`` toggle) to swap in
the real ``call_answer_model`` and smoke-test the live model against fixture
retrieval. CI never sets it, so the recorded path always runs there.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from app.routers.ask import REFUSAL_MESSAGE_KEY, REFUSAL_TEXT, run_ask
from app.services.ask.filters import AskFilters
from app.services.ask.prompt import BuiltPrompt, ModelAnswer, call_answer_model
from app.services.ask.retrieve import RetrievedDoc

EVAL_SET_PATH = Path(__file__).with_name("ask_eval_set.yaml")
VALID_CATEGORIES = {"exact", "fuzzy", "semantic", "price_filtered", "no_answer"}
LIVE_MODE = os.environ.get("ASK_EVAL_LIVE", "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class FixtureDoc:
    entity_kind: str
    entity_id: str
    title: str
    body: str = ""
    price_min_ngwee: int | None = None
    price_max_ngwee: int | None = None


@dataclass(frozen=True)
class RecordedAnswer:
    answer_text: str
    cited_entity_ids: list[str]
    model: str
    total_tokens: int


@dataclass(frozen=True)
class Expect:
    refused: bool
    cited_ids: list[str] = field(default_factory=list)
    zmw_contains: str | None = None


@dataclass(frozen=True)
class EvalEntry:
    id: str
    category: str
    query: str
    fixture_docs: list[FixtureDoc]
    recorded_answer: RecordedAnswer
    expect: Expect


def _load_entries() -> list[EvalEntry]:
    raw: Any = yaml.safe_load(EVAL_SET_PATH.read_text(encoding="utf-8"))
    entries: list[EvalEntry] = []
    for item in raw:
        docs = [FixtureDoc(**doc) for doc in item["fixture_docs"]]
        entries.append(
            EvalEntry(
                id=str(item["id"]),
                category=str(item["category"]),
                query=str(item["query"]),
                fixture_docs=docs,
                recorded_answer=RecordedAnswer(**item["recorded_answer"]),
                expect=Expect(**item["expect"]),
            )
        )
    return entries


EVAL_ENTRIES = _load_entries()


# ---------------------------------------------------------------------------
# Deterministic fakes (mirror tests/test_ask.py's ask_cache stub)
# ---------------------------------------------------------------------------


class _FakeCacheQuery:
    """Always a cache miss on read; records upserts (writes are ignored)."""

    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def select(self, *_columns: str) -> _FakeCacheQuery:
        return self

    def eq(self, *_args: Any) -> _FakeCacheQuery:
        return self

    def gt(self, *_args: Any) -> _FakeCacheQuery:
        return self

    def maybe_single(self) -> _FakeCacheQuery:
        return self

    def upsert(self, payload: dict[str, Any], *, on_conflict: str) -> _FakeCacheQuery:
        self._store[payload[on_conflict]] = payload
        return self

    def execute(self) -> Any:
        return type("Resp", (), {"data": None})()


class _FakeClient:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def table(self, name: str) -> _FakeCacheQuery:
        assert name == "ask_cache"
        return _FakeCacheQuery(self._cache)


@pytest.fixture(autouse=True)
def _stub_ask_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the eval from M06-P03 quota enforcement (covered elsewhere)."""
    import app.services.ask.quota as quota

    monkeypatch.setattr(quota, "check_and_reserve", lambda **_: None)
    monkeypatch.setattr(quota, "record_answer", lambda **_: None)


def _to_retrieved(docs: list[FixtureDoc]) -> list[RetrievedDoc]:
    return [
        RetrievedDoc(
            entity_kind=doc.entity_kind,
            entity_id=doc.entity_id,
            title=doc.title,
            body=doc.body,
            price_min_ngwee=doc.price_min_ngwee,
            price_max_ngwee=doc.price_max_ngwee,
            rrf_score=1.0,
        )
        for doc in docs
    ]


# ---------------------------------------------------------------------------
# Eval-set shape guard
# ---------------------------------------------------------------------------


def test_eval_set_shape() -> None:
    assert len(EVAL_ENTRIES) == 20
    assert len({entry.id for entry in EVAL_ENTRIES}) == 20
    assert all(entry.category in VALID_CATEGORIES for entry in EVAL_ENTRIES)

    traps = [entry for entry in EVAL_ENTRIES if entry.category == "no_answer"]
    assert len(traps) >= 4
    assert all(entry.expect.refused and not entry.fixture_docs for entry in traps)

    priced = [entry for entry in EVAL_ENTRIES if entry.category == "price_filtered"]
    assert len(priced) >= 3


# ---------------------------------------------------------------------------
# Grounding gate (20 questions)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", EVAL_ENTRIES, ids=[entry.id for entry in EVAL_ENTRIES])
async def test_ask_grounding(entry: EvalEntry) -> None:
    client = _FakeClient()
    docs = _to_retrieved(entry.fixture_docs)
    fixture_ids = {doc.entity_id for doc in docs}

    async def _fixture_retriever(
        _client: Any, *, query: str, filters: AskFilters
    ) -> list[RetrievedDoc]:
        return docs

    if LIVE_MODE:
        model_caller: Any = call_answer_model
    else:
        recorded = entry.recorded_answer

        async def _recorded_model(_prompt: BuiltPrompt) -> ModelAnswer:
            return ModelAnswer(
                answer_text=recorded.answer_text,
                cited_entity_ids=list(recorded.cited_entity_ids),
                model=recorded.model,
                total_tokens=recorded.total_tokens,
            )

        model_caller = _recorded_model

    response = await run_ask(
        client=client,
        query=entry.query,
        user_id=None,
        guest_key="ip:127.0.0.1",
        model_caller=model_caller,
        retriever=_fixture_retriever,
    )

    cited = [citation.entity_id for citation in response.citations]

    # (1) No fabrication: every cited id was actually retrieved.
    assert set(cited) <= fixture_ids, (
        f"{entry.id}: fabricated citation leaked: {set(cited) - fixture_ids}"
    )

    # (2) Refusal behaviour matches expectation.
    assert response.refused is entry.expect.refused, (
        f"{entry.id}: expected refused={entry.expect.refused}, got {response.refused}"
    )
    if entry.expect.refused:
        assert response.answer == REFUSAL_TEXT
        assert response.message_key == REFUSAL_MESSAGE_KEY
        assert cited == []

    # Live mode uses a non-deterministic model; only invariants (1)+(2) hold.
    if LIVE_MODE:
        return

    # (3a) Exact grounded citation set after fabricated-id stripping.
    assert sorted(cited) == sorted(entry.expect.cited_ids), (
        f"{entry.id}: cited {sorted(cited)} != expected {sorted(entry.expect.cited_ids)}"
    )

    # (3b) ZMW ngwee -> decimal correctness in the citation price_display.
    if entry.expect.zmw_contains is not None:
        displays = [citation.price_display or "" for citation in response.citations]
        assert any(entry.expect.zmw_contains in display for display in displays), (
            f"{entry.id}: {entry.expect.zmw_contains!r} not in {displays}"
        )
