"""Coverage sweep: every mutating route must declare a rate-limit policy.

Pure unit test — no DB, no network. It builds the app in-process and asserts
the startup coverage gate both passes for the real route set and has teeth
(raises for a synthetic unregistered mutating route).
"""

from __future__ import annotations

import pytest
from app.core.ratelimit_policies import (
    EXEMPT_ROUTE_IDS,
    MUTATING_METHODS,
    POLICIES,
    UncoveredMutatingRoutesError,
    assert_all_mutating_routes_covered,
    iter_mutating_route_ids,
    policy_for,
    route_id,
)
from app.main import create_app
from fastapi import FastAPI


def _built_app() -> FastAPI:
    # create_app() itself runs the gate at construction time; if the current
    # route set were uncovered this call would already raise.
    return create_app()


def test_every_mutating_route_has_a_policy() -> None:
    app = _built_app()
    # Explicit call (in addition to the one inside create_app) documents intent.
    assert_all_mutating_routes_covered(app)

    mutating = iter_mutating_route_ids(app)
    covered = set(POLICIES) | EXEMPT_ROUTE_IDS
    uncovered = sorted(mutating - covered)
    assert uncovered == [], f"uncovered mutating routes: {uncovered}"
    # Sanity: the app really does expose a non-trivial mutating surface.
    assert len(mutating) > 100


def test_registry_has_no_stale_entries() -> None:
    """Every POLICIES key and exemption must map to a real mutating route.

    Guards against drift/typos: a policy for a route that no longer exists is
    dead weight and would mask a genuine gap if a real route reused the id.
    """
    app = _built_app()
    live = iter_mutating_route_ids(app)
    stale_policies = sorted(set(POLICIES) - live)
    stale_exemptions = sorted(EXEMPT_ROUTE_IDS - live)
    assert stale_policies == [], f"stale policy entries: {stale_policies}"
    assert stale_exemptions == [], f"stale exemptions: {stale_exemptions}"


def test_exemptions_are_only_webhooks() -> None:
    # The exemption allowlist must stay minimal and documented.
    assert EXEMPT_ROUTE_IDS == frozenset(
        {"POST /webhooks/lenco", "POST /webhooks/whatsapp"}
    )
    # Exempt routes must never also carry a policy (no double-accounting).
    assert not (set(POLICIES) & EXEMPT_ROUTE_IDS)


def test_synthetic_unregistered_route_raises() -> None:
    """The gate must have teeth: an unregistered mutating route fails."""
    app = FastAPI()

    @app.post("/synthetic/unregistered")
    async def _synthetic() -> dict[str, str]:  # pragma: no cover - never called
        return {"ok": "true"}

    with pytest.raises(UncoveredMutatingRoutesError) as exc:
        assert_all_mutating_routes_covered(app)
    assert "POST /synthetic/unregistered" in str(exc.value)


def test_synthetic_get_route_is_not_flagged() -> None:
    """Non-mutating (GET) routes are never required to be registered."""
    app = FastAPI()

    @app.get("/synthetic/read-only")
    async def _read_only() -> dict[str, str]:  # pragma: no cover - never called
        return {"ok": "true"}

    # No mutating routes at all → gate passes cleanly.
    assert_all_mutating_routes_covered(app)
    assert iter_mutating_route_ids(app) == set()


def test_policy_lookup_helpers() -> None:
    assert route_id("post", "/orders") == "POST /orders"
    assert policy_for("POST", "/orders") is not None
    assert policy_for("POST", "/webhooks/lenco") is None  # exempt → no policy
    assert policy_for("POST", "/nope/does-not-exist") is None


def test_mutating_methods_constant() -> None:
    assert MUTATING_METHODS == frozenset({"POST", "PUT", "PATCH", "DELETE"})
