"""Analytics v2 envelope (plan 1A-01): registry parity, validation, v1 normalisation.

Pure — no DB, no app. The registry JSON in ``packages/analytics`` is the single
source of truth; this suite fails if the Python mirror drifts from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.services.analytics.envelope import (
    ENVELOPE_VERSION,
    MAX_EVENTS_PER_BATCH,
    REGISTRY,
    SERVER_RECORDED_EVENTS,
    SOURCE_APPS,
    RawBatch,
    normalize_batch,
)

REGISTRY_JSON = (
    Path(__file__).resolve().parents[3] / "packages" / "analytics" / "registry" / "events.v2.json"
)

NOW_MS = 1_800_000_000_000
ANON = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PRODUCT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
LISTING = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def _eid(n: int) -> str:
    return f"eeeeeeee-eeee-4eee-8eee-{n:012d}"


def _v2(events: list[dict[str, Any]], **extra: Any) -> RawBatch:
    body: dict[str, Any] = {
        "v": 2,
        "session_id": ANON,
        "anon": ANON,
        "sid": SID,
        "app": "customer",
        "events": events,
    }
    body.update(extra)
    return RawBatch.model_validate(body)


def _pv(n: int = 1, **props: Any) -> dict[str, Any]:
    return {
        "event": "product_view",
        "ev": 1,
        "id": _eid(n),
        "seq": n,
        "ts": NOW_MS,
        "page": "pdp",
        "props": {"product_id": PRODUCT, **props},
    }


class TestRegistryParity:
    def test_python_registry_matches_json(self) -> None:
        data = json.loads(REGISTRY_JSON.read_text())
        assert data["envelope_version"] == ENVELOPE_VERSION
        assert set(data["events"]) == set(REGISTRY)
        for name, spec in data["events"].items():
            py = REGISTRY[name]
            assert py.version == spec["version"], name
            assert py.entity_type == spec["entity_type"], name
            assert py.entity_prop == spec["entity_prop"], name
            assert py.props == spec["props"], name
        assert set(data["server_recorded"]) == SERVER_RECORDED_EVENTS
        assert tuple(data["source_apps"]) == SOURCE_APPS

    def test_no_money_or_pii_prop_registered(self) -> None:
        for name, spec in REGISTRY.items():
            for key in spec.props:
                assert not key.endswith("_ngwee"), f"{name}.{key}: money is authoritative-only"
                assert key not in {"phone", "email", "term", "url", "referrer"}, name


class TestV2Validation:
    def test_valid_product_view(self) -> None:
        out = normalize_batch(_v2([_pv(listing_id=LISTING)]), now_ms=NOW_MS)
        assert out.rejected == 0 and out.skipped == 0
        [row] = out.rows
        assert row.event_id == _eid(1)
        assert row.event_name == "product_view"
        assert row.anon_id == ANON and row.session_id == SID
        assert row.entity_type == "product" and row.entity_id == PRODUCT
        assert row.props == {"product_id": PRODUCT, "listing_id": LISTING}
        assert row.page_key == "pdp" and row.seq == 1 and row.client_ts_ms == NOW_MS

    def test_unknown_props_dropped(self) -> None:
        out = normalize_batch(_v2([_pv(colour="red")]), now_ms=NOW_MS)
        assert out.rows[0].props == {"product_id": PRODUCT}

    @pytest.mark.parametrize("key", ["phone", "email", "Term", "referrer", "total_ngwee"])
    def test_pii_or_money_key_rejects_event(self, key: str) -> None:
        ev = _pv()
        ev["props"][key] = "x"
        out = normalize_batch(_v2([ev]), now_ms=NOW_MS)
        assert out.rows == [] and out.rejected_invalid == 1

    def test_missing_required_prop_rejected(self) -> None:
        ev = _pv()
        ev["props"] = {}
        out = normalize_batch(_v2([ev]), now_ms=NOW_MS)
        assert out.rejected_invalid == 1

    def test_invalid_optional_prop_dropped_not_rejected(self) -> None:
        out = normalize_batch(_v2([_pv(listing_id="nope")]), now_ms=NOW_MS)
        assert out.rows[0].props == {"product_id": PRODUCT}

    def test_unknown_event_rejected_and_server_recorded_skipped(self) -> None:
        out = normalize_batch(
            _v2(
                [
                    {"event": "mouse_move", "id": _eid(1), "props": {}},
                    {"event": "cart_add", "id": _eid(2), "props": {}},
                ]
            ),
            now_ms=NOW_MS,
        )
        assert out.rejected_unknown == 1 and out.skipped == 1 and out.rows == []

    def test_v2_requires_event_id(self) -> None:
        ev = _pv()
        ev["id"] = "not-a-uuid"
        assert normalize_batch(_v2([ev]), now_ms=NOW_MS).rejected_invalid == 1

    def test_version_mismatch_rejected(self) -> None:
        ev = _pv()
        ev["ev"] = 99
        assert normalize_batch(_v2([ev]), now_ms=NOW_MS).rejected_invalid == 1

    def test_duplicate_ids_in_batch_collapse(self) -> None:
        out = normalize_batch(_v2([_pv(1), _pv(1)]), now_ms=NOW_MS)
        assert len(out.rows) == 1

    def test_timestamp_clamped(self) -> None:
        ev_old, ev_future = _pv(1), _pv(2)
        ev_old["ts"] = NOW_MS - 8 * 86_400_000
        ev_future["ts"] = NOW_MS + 10 * 60_000
        out = normalize_batch(_v2([ev_old, ev_future]), now_ms=NOW_MS)
        assert [r.client_ts_ms for r in out.rows] == [None, None]

    def test_bad_page_key_and_seq_nulled(self) -> None:
        ev = _pv()
        ev["page"] = "/en/p/secret-slug?q=1"
        ev["seq"] = -4
        row = normalize_batch(_v2([ev]), now_ms=NOW_MS).rows[0]
        assert row.page_key is None and row.seq is None

    def test_int_bool_enum_specs(self) -> None:
        good = {
            "event": "search",
            "id": _eid(1),
            "props": {"zero_result": False, "result_count": 3, "normalized_term": "x"},
        }
        bad = {
            "event": "search",
            "id": _eid(2),
            "props": {"zero_result": "no", "result_count": True},
        }
        share = {
            "event": "product_share",
            "id": _eid(3),
            "props": {"product_id": PRODUCT, "channel": "telegram"},
        }
        out = normalize_batch(_v2([good, bad, share]), now_ms=NOW_MS)
        # normalized_term is not registered for v2 search: the term lives only in
        # search_query_log under its own retention (plan §R-E).
        assert out.rows[0].props == {"zero_result": False, "result_count": 3}
        assert out.rows[1].props == {}
        assert out.rows[2].props == {"product_id": PRODUCT}

    def test_oversized_props_rejected(self) -> None:
        out = normalize_batch(_v2([_pv(blob="x" * 3_000)]), now_ms=NOW_MS)
        assert out.rejected_invalid == 1

    def test_batch_capped(self) -> None:
        events = [_pv(i) for i in range(MAX_EVENTS_PER_BATCH + 3)]
        out = normalize_batch(_v2(events), now_ms=NOW_MS)
        assert len(out.rows) == MAX_EVENTS_PER_BATCH and out.rejected_invalid == 3

    def test_counts_only_mode_strips_ids(self) -> None:
        out = normalize_batch(_v2([_pv()], consent="denied"), now_ms=NOW_MS)
        assert out.rows[0].anon_id is None and out.rows[0].session_id is None

    def test_invalid_ids_become_null_and_unknown_app_defaults(self) -> None:
        out = normalize_batch(_v2([_pv()], anon="x", sid="y", app="server"), now_ms=NOW_MS)
        row = out.rows[0]
        assert row.anon_id is None and row.session_id is None and row.source_app == "customer"

    def test_user_id_passthrough(self) -> None:
        out = normalize_batch(_v2([_pv()]), now_ms=NOW_MS, user_id=SID)
        assert out.rows[0].user_id == SID


class TestV1Normalisation:
    def test_v1_batch_maps_legacy_session_to_anon(self) -> None:
        batch = RawBatch.model_validate(
            {
                "session_id": ANON,
                "events": [{"event": "product_view", "props": {"product_id": PRODUCT}}],
            }
        )
        out = normalize_batch(batch, now_ms=NOW_MS)
        [row] = out.rows
        assert row.anon_id == ANON and row.session_id is None
        assert row.page_key is None
        assert len(row.event_id) == 36  # synthesised server-side

    def test_v1_ignores_v2_ids_and_page(self) -> None:
        batch = RawBatch.model_validate(
            {
                "session_id": ANON,
                "events": [
                    {
                        "event": "product_view",
                        "id": "zzz",
                        "page": "pdp",
                        "props": {"product_id": PRODUCT},
                    }
                ],
            }
        )
        row = normalize_batch(batch, now_ms=NOW_MS).rows[0]
        assert row.page_key is None and row.event_id != "zzz"

    def test_v1_search_and_funnel_events(self) -> None:
        batch = RawBatch.model_validate(
            {
                "events": [
                    {
                        "event": "search",
                        "props": {"normalized_term": "phones", "zero_result": True},
                    },
                    {"event": "order_placed", "props": {"total_ngwee": 100}},
                ]
            }
        )
        out = normalize_batch(batch, now_ms=NOW_MS)
        assert out.skipped == 1
        assert out.rows[0].props == {"zero_result": True}
