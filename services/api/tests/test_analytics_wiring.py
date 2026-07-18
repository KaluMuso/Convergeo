"""Task 1 wiring: the dormant analytics writers are now invoked from live paths.

DB-free unit tests. They assert the *call wiring* and the fire-and-forget contract,
not the DB round-trips (those live in test_search_analytics.py / test_funnel.py):

  * ``run_search`` invokes ``log_search_query`` with per-entity counts, the
    zero-result flag, and the caller ``user_id``;
  * ``run_ask`` invokes ``log_ask_query`` with the resolved ``usd_micros`` at each
    resolution point (cached / refusal / answered);
  * the funnel ``emit_*`` wrappers are fire-and-forget — a raising ``record_event``
    is swallowed — so an analytics write can never break a cart/checkout/payment/
    order request.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.routers import ask as ask_mod
from app.routers.ask import run_ask
from app.services import search as search_mod
from app.services.analytics import funnel as funnel_mod
from app.services.analytics.funnel import record_event_best_effort
from app.services.cart.events import emit_cart_add, emit_checkout_start, emit_step_complete
from app.services.orders.events import emit_order_placed_funnel, emit_payment_start_funnel
from app.services.search import SearchHit, run_search


def _hit(entity_kind: str, entity_id: str) -> SearchHit:
    return SearchHit(
        id=f"row-{entity_id}",
        entity_kind=entity_kind,
        entity_id=entity_id,
        title="Title",
        rrf_score=1.0,
    )


async def _no_embedding(_term: str) -> None:
    return None


# ---------------------------------------------------------------------------
# Search → log_search_query
# ---------------------------------------------------------------------------
class TestSearchWiring:
    async def test_run_search_logs_entity_counts_and_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logged: dict[str, Any] = {}
        monkeypatch.setattr(search_mod, "expand_query", lambda _client, q: q)
        monkeypatch.setattr(
            search_mod,
            "call_search_rrf",
            lambda *a, **k: [_hit("product", "p1"), _hit("product", "p2"), _hit("service", "s1")],
        )
        monkeypatch.setattr(search_mod, "log_search_query", lambda **kw: logged.update(kw))

        resp = await run_search(
            MagicMock(),
            query="  Blue Widget ",
            embedding_fetcher=_no_embedding,
            include_wholesale=True,  # skip the wholesale-drop DB call
            user_id="user-123",
        )

        assert resp.total == 3
        assert logged["term"] == "Blue Widget"
        assert logged["entity_counts"] == {"product": 2, "service": 1}
        assert logged["zero_result"] is False
        assert logged["user_id"] == "user-123"

    async def test_run_search_zero_result_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logged: dict[str, Any] = {}
        monkeypatch.setattr(search_mod, "expand_query", lambda _client, q: q)
        monkeypatch.setattr(search_mod, "call_search_rrf", lambda *a, **k: [])
        monkeypatch.setattr(search_mod, "log_search_query", lambda **kw: logged.update(kw))

        await run_search(
            MagicMock(),
            query="no matches here",
            embedding_fetcher=_no_embedding,
            include_wholesale=True,
        )

        assert logged["zero_result"] is True
        assert logged["entity_counts"] == {}
        assert logged["user_id"] is None


# ---------------------------------------------------------------------------
# Ask → log_ask_query (spend derived with the kill-switch's tokens_to_usd_micros)
# ---------------------------------------------------------------------------
def _silence_ask_side_effects(monkeypatch: pytest.MonkeyPatch, logged: dict[str, Any]) -> None:
    monkeypatch.setattr(ask_mod, "cache_write", lambda *a, **k: None)
    monkeypatch.setattr(ask_mod, "_optional_quota_check_and_reserve", lambda **k: None)
    monkeypatch.setattr(ask_mod, "_optional_quota_record_answer", lambda **k: None)
    monkeypatch.setattr(ask_mod, "log_ask_query", lambda **kw: logged.update(kw))


class TestAskWiring:
    async def test_answered_logs_resolved_spend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logged: dict[str, Any] = {}
        _silence_ask_side_effects(monkeypatch, logged)
        monkeypatch.setattr(ask_mod, "cache_lookup", lambda *a, **k: None)
        monkeypatch.setattr(ask_mod, "build_prompt", lambda **k: "prompt")
        monkeypatch.setattr(
            ask_mod,
            "validate_citations",
            lambda **k: SimpleNamespace(answer_text="Here you go", citations=[]),
        )
        monkeypatch.setattr(ask_mod, "tokens_to_usd_micros", lambda **k: 4200)

        async def _retriever(_client: Any, *, query: str, filters: Any) -> list[Any]:
            return [SimpleNamespace(entity_id="p1")]

        async def _model(_prompt: Any) -> Any:
            return SimpleNamespace(
                answer_text="Here you go", cited_entity_ids=["p1"], model="x", total_tokens=900
            )

        resp = await run_ask(
            client=MagicMock(),
            query="phones?",
            user_id="u1",
            guest_key="ip:1",
            model_caller=_model,
            retriever=_retriever,
        )

        assert resp.refused is False
        assert logged == {
            "term": "phones?",
            "usd_micros": 4200,
            "zero_result": False,
            "user_id": "u1",
        }

    async def test_refusal_logs_zero_spend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logged: dict[str, Any] = {}
        _silence_ask_side_effects(monkeypatch, logged)
        monkeypatch.setattr(ask_mod, "cache_lookup", lambda *a, **k: None)
        # tokens_to_usd_micros left REAL: tokens=0 short-circuits to 0 with no DB read.

        async def _retriever(_client: Any, *, query: str, filters: Any) -> list[Any]:
            return []  # no docs → refusal

        resp = await run_ask(
            client=MagicMock(),
            query="obscure thing",
            user_id=None,
            guest_key="ip:1",
            retriever=_retriever,
        )

        assert resp.refused is True
        assert logged["usd_micros"] == 0
        assert logged["zero_result"] is True
        assert logged["user_id"] is None

    async def test_cached_logs_zero_spend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logged: dict[str, Any] = {}
        _silence_ask_side_effects(monkeypatch, logged)
        monkeypatch.setattr(
            ask_mod,
            "cache_lookup",
            lambda *a, **k: {"answer": {"answer_text": "Cached answer", "citations": []}},
        )

        resp = await run_ask(
            client=MagicMock(), query="cached q", user_id="u2", guest_key="ip:1"
        )

        assert resp.cached is True
        assert logged["usd_micros"] == 0
        assert logged["term"] == "cached q"


# ---------------------------------------------------------------------------
# Funnel emit_* → fire-and-forget (never break a money path)
# ---------------------------------------------------------------------------
class TestFunnelFireAndForget:
    def test_best_effort_swallows_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**_k: Any) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(funnel_mod, "record_event", _boom)
        result = record_event_best_effort(stage="cart_add", checkout_group_id=None, snapshot={})
        assert result is None

    def test_best_effort_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            funnel_mod,
            "record_event",
            lambda **k: {"id": "x", "stage": k["stage"], "created_at": "t"},
        )
        row = record_event_best_effort(stage="order_placed", checkout_group_id="g", snapshot={})
        assert row == {"id": "x", "stage": "order_placed", "created_at": "t"}

    @pytest.mark.parametrize(
        "emit",
        [
            lambda: emit_cart_add(checkout_group_id=None, customer_id=None, snapshot={}),
            lambda: emit_checkout_start(checkout_group_id="g", customer_id="c", snapshot={}),
            lambda: emit_step_complete(checkout_group_id="g", customer_id="c", snapshot={}),
            lambda: emit_payment_start_funnel(checkout_group_id="g", customer_id="c", snapshot={}),
            lambda: emit_order_placed_funnel(checkout_group_id="g", customer_id="c", snapshot={}),
        ],
    )
    def test_emit_wrappers_never_raise(
        self, monkeypatch: pytest.MonkeyPatch, emit: Any
    ) -> None:
        def _boom(**_k: Any) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(funnel_mod, "record_event", _boom)
        assert emit() is None  # fire-and-forget: the cart/checkout/order request is never broken
