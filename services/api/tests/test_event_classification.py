"""Events Wave A · M10-P10 — classification, visibility & policy foundation.

Isolation-clean: no DB/network. Covers the per-type policy map, the organiser
private-access-code guard, and the public discovery visibility rules (browse hides
unlisted/private; detail resolves unlisted by link and gates private by code) against
a tiny fake Supabase store. Money-free pebble.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from app.errors import AppError
from app.routers.events_public import build_browse_response, build_detail_response
from app.routers.organiser_events import _require_access_code_for_private
from app.services.events.policy import (
    DEFAULT_EVENT_TYPE,
    EVENT_TYPE_POLICY,
    EVENT_TYPES,
    policy_for,
)

VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
REF = datetime(2026, 7, 9, 12, 0, tzinfo=ZoneInfo("Africa/Lusaka"))


# --------------------------------------------------------------------------- #
# Policy map
# --------------------------------------------------------------------------- #
def test_every_event_type_has_a_policy() -> None:
    # No enum value may lack a policy entry (single source of truth, no gaps).
    assert set(EVENT_TYPE_POLICY) == set(EVENT_TYPES)
    for event_type, policy in EVENT_TYPE_POLICY.items():
        assert policy.event_type == event_type


def test_policy_for_defaults_on_unknown_or_none() -> None:
    default = EVENT_TYPE_POLICY[DEFAULT_EVENT_TYPE]
    assert policy_for(None) is default
    assert policy_for("no_such_type") is default
    assert policy_for("multi_day") is EVENT_TYPE_POLICY["multi_day"]


def test_policy_shapes_match_intent() -> None:
    assert EVENT_TYPE_POLICY["free"].paid is False
    assert EVENT_TYPE_POLICY["free"].escrow_schedule == "none"
    assert EVENT_TYPE_POLICY["multi_day"].multi_instance is True
    assert EVENT_TYPE_POLICY["experience"].named_tickets_default is True
    assert EVENT_TYPE_POLICY["single"].escrow_schedule == "date_anchored"


# --------------------------------------------------------------------------- #
# Organiser private-access-code guard
# --------------------------------------------------------------------------- #
def test_private_requires_access_code() -> None:
    with pytest.raises(AppError) as exc:
        _require_access_code_for_private("private", None)
    assert exc.value.http_status == 422
    with pytest.raises(AppError):
        _require_access_code_for_private("private", "   ")


def test_non_private_needs_no_code() -> None:
    _require_access_code_for_private("public", None)
    _require_access_code_for_private("unlisted", None)
    _require_access_code_for_private("private", "secret123")  # ok with a code


# --------------------------------------------------------------------------- #
# Fake Supabase store (events + instances + ticket_types + tickets)
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: _Store, table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._maybe_single = False

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self._filters.append(("in", column, values))
        return self

    def order(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def maybe_single(self) -> _Query:
        self._maybe_single = True
        return self

    def execute(self) -> _Resp:
        rows = [dict(r) for r in getattr(self._store, self._table)]
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            else:
                rows = [r for r in rows if r.get(col) in val]
        if self._maybe_single:
            return _Resp(rows[0] if rows else None)
        return _Resp(rows)


class _Store:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.event_instances: list[dict[str, Any]] = []
        self.ticket_types: list[dict[str, Any]] = []
        self.tickets: list[dict[str, Any]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def _vendor() -> dict[str, Any]:
    return {
        "id": VENDOR,
        "slug": "event-house",
        "display_name": "Event House",
        "preferred_badge": False,
        "logo_url": None,
        "description": None,
        "vendor_locations": [],
    }


def _event(
    event_id: str, slug: str, *, visibility: str, access_code: str | None = None
) -> dict[str, Any]:
    return {
        "id": event_id,
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": "desc",
        "venue": "Lusaka",
        "lat": None,
        "lng": None,
        "images": [],
        "status": "published",
        "category_slug": "workshops",
        "landmark": None,
        "event_type": "single",
        "visibility": visibility,
        "access_code": access_code,
        "organiser_vendor_id": VENDOR,
        "vendors": _vendor(),
    }


def _instance(event_id: str, instance_id: str) -> dict[str, Any]:
    return {
        "id": instance_id,
        "event_id": event_id,
        "starts_at": "2026-07-10T20:00:00+02:00",
        "ends_at": None,
        "capacity": 100,
    }


def _ticket_type(event_id: str, tt_id: str) -> dict[str, Any]:
    return {
        "id": tt_id,
        "event_id": event_id,
        "kind": "fixed",
        "name": "GA",
        "price_ngwee": 50_000,
        "qty_cap": 100,
    }


def _seed() -> _Store:
    store = _Store()
    store.events = [
        _event("e-pub", "public-gig", visibility="public"),
        _event("e-unl", "unlisted-gig", visibility="unlisted"),
        _event("e-prv", "private-gig", visibility="private", access_code="vip-2026"),
    ]
    store.event_instances = [
        _instance("e-pub", "i-pub"),
        _instance("e-unl", "i-unl"),
        _instance("e-prv", "i-prv"),
    ]
    store.ticket_types = [
        _ticket_type("e-pub", "tt-pub"),
        _ticket_type("e-unl", "tt-unl"),
        _ticket_type("e-prv", "tt-prv"),
    ]
    return store


# --------------------------------------------------------------------------- #
# Browse — public only
# --------------------------------------------------------------------------- #
def test_browse_lists_only_public_events() -> None:
    store = _seed()
    result = build_browse_response(store, ref=REF)
    slugs = {item.slug for item in result.items}
    assert slugs == {"public-gig"}  # unlisted + private are hidden from browse


# --------------------------------------------------------------------------- #
# Detail — unlisted by link, private by code
# --------------------------------------------------------------------------- #
def test_detail_unlisted_resolves_without_code() -> None:
    store = _seed()
    detail = build_detail_response(store, "unlisted-gig")
    assert detail.slug == "unlisted-gig"
    assert detail.visibility == "unlisted"
    assert detail.event_type == "single"
    # The public detail model never carries the access code.
    assert not hasattr(detail, "access_code")


def test_detail_private_without_code_is_404() -> None:
    store = _seed()
    with pytest.raises(AppError) as exc:
        build_detail_response(store, "private-gig")
    assert exc.value.http_status == 404


def test_detail_private_with_wrong_code_is_404() -> None:
    store = _seed()
    with pytest.raises(AppError) as exc:
        build_detail_response(store, "private-gig", access_code="nope")
    assert exc.value.http_status == 404


def test_detail_private_with_correct_code_resolves() -> None:
    store = _seed()
    detail = build_detail_response(store, "private-gig", access_code="vip-2026")
    assert detail.slug == "private-gig"
    assert detail.visibility == "private"
