"""Central rate-limit policy registry + startup coverage gate.

This module sits ON TOP of ``app.core.ratelimit`` (the enforcement primitive —
``bump_rate_counter`` / ``raise_rate_limited``). It does **not** re-implement
enforcement. Instead it provides:

1. A declarative ``POLICIES`` registry: every mutating route (POST/PUT/PATCH/
   DELETE) MUST declare a :class:`RateLimitPolicy` here, keyed by a stable route
   id ``"{METHOD} {path_template}"``.
2. :func:`assert_all_mutating_routes_covered` — walked once at app startup. It
   enumerates every mutating route in the live FastAPI route table, subtracts an
   EXPLICIT, documented exemption allowlist (webhooks only — see
   ``EXEMPT_ROUTE_IDS``), and raises if any mutating route is not registered.
   A new unregistered mutating route therefore fails CI immediately.

The registry is the single declarative source of truth; existing per-route
enforcement continues to call the ``ratelimit`` primitive. :func:`policy_for`
lets a future shared dependency/middleware look a policy up by method + path
without editing individual routers.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

from starlette.routing import Route

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Declarative rate-limit for one route.

    ``scope`` is the counter bucket passed to ``bump_rate_counter``; ``limit``
    is the max requests inside ``window``.
    """

    scope: str
    limit: int
    window: timedelta


# --- Policy tiers -----------------------------------------------------------
# Reusable tiers keep the registry declarative and reviewable. Windows are
# per-minute unless a longer burst window is warranted.
STANDARD_WRITE = RateLimitPolicy(scope="write_standard", limit=60, window=timedelta(minutes=1))
SENSITIVE_WRITE = RateLimitPolicy(scope="write_sensitive", limit=10, window=timedelta(minutes=1))
PAYMENT_WRITE = RateLimitPolicy(scope="write_payment", limit=20, window=timedelta(minutes=1))
ADMIN_WRITE = RateLimitPolicy(scope="write_admin", limit=120, window=timedelta(minutes=1))
# Internal cron/n8n ticks are called by trusted schedulers on a shared secret;
# they get a generous machine-to-machine ceiling rather than a human one.
INTERNAL_CRON = RateLimitPolicy(scope="internal_cron", limit=240, window=timedelta(minutes=1))


# --- Exemption allowlist (EXPLICIT + documented — no silent gaps) -----------
# Only inbound provider webhooks are exempt: they are signature-verified and
# idempotent, and Lenco retries them (30min x 24h). Rate-limiting them would
# drop legitimate provider retries. Health/readiness probes are GET-only and so
# are never in the mutating set to begin with. Nothing else may be added here
# without a written rationale.
EXEMPT_ROUTE_IDS: frozenset[str] = frozenset(
    {
        "POST /webhooks/lenco",
        "POST /webhooks/whatsapp",
    }
)


# --- The registry: every mutating route MUST appear here (or be exempt) ------
# Keyed by "{METHOD} {path_template}". Generated from the complete batch-2
# route set (M11-P05 job-completion + M15-P07 invoices merged) and asserted at
# startup. Adding a mutating route without an entry here fails the sweep.
POLICIES: dict[str, RateLimitPolicy] = {
    "DELETE /account/addresses/{address_id}": STANDARD_WRITE,
    "DELETE /admin/translations/overrides": ADMIN_WRITE,
    "DELETE /cart/items/{listing_id}": STANDARD_WRITE,
    "DELETE /merch/slots/{slot_id}": ADMIN_WRITE,
    "DELETE /organiser/ticket-types/{ticket_type_id}": STANDARD_WRITE,
    "DELETE /vendor/listings/{listing_id}": STANDARD_WRITE,
    "DELETE /vendor/listings/{listing_id}/images/{image_id}": STANDARD_WRITE,
    "PATCH /account/addresses/{address_id}": STANDARD_WRITE,
    "PATCH /account/preferences": STANDARD_WRITE,
    "PATCH /account/profile": STANDARD_WRITE,
    "PATCH /cart/items/{listing_id}": STANDARD_WRITE,
    "PATCH /config/categories/{category_id}": ADMIN_WRITE,
    "PATCH /config/commissions/{category_key}": ADMIN_WRITE,
    "PATCH /config/delivery-zones/{zone_key}": ADMIN_WRITE,
    "PATCH /config/flags/{flag}": ADMIN_WRITE,
    "PATCH /config/platform/{key}": ADMIN_WRITE,
    "PATCH /merch/slots/{slot_id}": ADMIN_WRITE,
    "PATCH /organiser/events/{event_id}": STANDARD_WRITE,
    "PATCH /organiser/ticket-types/{ticket_type_id}": STANDARD_WRITE,
    "PATCH /vendor/listings/{listing_id}": STANDARD_WRITE,
    "PATCH /vendor/listings/{listing_id}/images/reorder": STANDARD_WRITE,
    "PATCH /vendor/listings/{listing_id}/stock": STANDARD_WRITE,
    "PATCH /vendor/profile": STANDARD_WRITE,
    "PATCH /vendor/services/{service_id}": STANDARD_WRITE,
    "POST /account/addresses": STANDARD_WRITE,
    "POST /account/delete": SENSITIVE_WRITE,
    "POST /account/export": SENSITIVE_WRITE,
    "POST /admin/business/{buyer_id}/reject": ADMIN_WRITE,
    "POST /admin/business/{buyer_id}/verify": ADMIN_WRITE,
    "POST /admin/echo": ADMIN_WRITE,
    "POST /admin/orders/{order_id}/cod/confirm-collection": PAYMENT_WRITE,
    "POST /admin/orders/{order_id}/cod/refuse-collection": PAYMENT_WRITE,
    "POST /ask": STANDARD_WRITE,
    "POST /auth/guard/otp-quota": SENSITIVE_WRITE,
    "POST /beta/feedback": STANDARD_WRITE,
    "POST /beta/invites": ADMIN_WRITE,
    "POST /beta/redeem": SENSITIVE_WRITE,
    "POST /business/apply": SENSITIVE_WRITE,
    "POST /cart/items": STANDARD_WRITE,
    "POST /cart/merge": STANDARD_WRITE,
    "POST /checkout/session": PAYMENT_WRITE,
    "POST /checkout/steps/contact": PAYMENT_WRITE,
    "POST /checkout/steps/fulfilment": PAYMENT_WRITE,
    "POST /checkout/steps/payment": PAYMENT_WRITE,
    "POST /config/categories/reorder": ADMIN_WRITE,
    "POST /disputes/orders/{order_id}": STANDARD_WRITE,
    "POST /disputes/vendor/orders/{order_id}/evidence/sign": SENSITIVE_WRITE,
    "POST /disputes/{dispute_id}/decide": ADMIN_WRITE,
    "POST /disputes/{dispute_id}/escalate": STANDARD_WRITE,
    "POST /disputes/{dispute_id}/resolve": STANDARD_WRITE,
    "POST /disputes/{dispute_id}/respond": STANDARD_WRITE,
    "POST /flags/{flag_id}/dismiss": ADMIN_WRITE,
    "POST /flags/{flag_id}/escalate-suspend": ADMIN_WRITE,
    "POST /flags/{flag_id}/remove": ADMIN_WRITE,
    "POST /flags/{flag_id}/unpublish": ADMIN_WRITE,
    "POST /flags/{flag_id}/warn-vendor": ADMIN_WRITE,
    "POST /internal/digest": INTERNAL_CRON,
    "POST /internal/dispatch/tick": INTERNAL_CRON,
    "POST /internal/embeddings/tick": INTERNAL_CRON,
    "POST /internal/event-release/tick": INTERNAL_CRON,
    "POST /internal/funnel/abandon-tick": INTERNAL_CRON,
    "POST /internal/job-completion/auto-confirm": INTERNAL_CRON,
    "POST /internal/jobs/expire-tick": INTERNAL_CRON,
    "POST /internal/n8n/abandoned-carts/tick": INTERNAL_CRON,
    "POST /internal/n8n/kyc-stalled/tick": INTERNAL_CRON,
    "POST /internal/n8n/low-stock/tick": INTERNAL_CRON,
    "POST /internal/n8n/payout-failures/tick": INTERNAL_CRON,
    "POST /internal/n8n/review-requests/tick": INTERNAL_CRON,
    "POST /internal/order-jobs/auto-confirm": INTERNAL_CRON,
    "POST /internal/order-jobs/auto-release": INTERNAL_CRON,
    "POST /internal/payment-sweeper/tick": INTERNAL_CRON,
    "POST /internal/payouts/execute": INTERNAL_CRON,
    "POST /internal/payouts/retry": INTERNAL_CRON,
    "POST /internal/payouts/tick": INTERNAL_CRON,
    "POST /internal/reconciliation/daily-report": INTERNAL_CRON,
    "POST /internal/reconciliation/poll-tick": INTERNAL_CRON,
    "POST /internal/reconciliation/webhook-drain-tick": INTERNAL_CRON,
    "POST /internal/release-job/tick": INTERNAL_CRON,
    "POST /internal/review-aggregate/tick": INTERNAL_CRON,
    "POST /internal/stock-sweeper/tick": INTERNAL_CRON,
    "POST /internal/tickets/issue-tick": INTERNAL_CRON,
    "POST /internal/tickets/release-tick": INTERNAL_CRON,
    "POST /jobs": STANDARD_WRITE,
    "POST /jobs/{job_id}/cancel": STANDARD_WRITE,
    "POST /jobs/{job_id}/complete": STANDARD_WRITE,
    "POST /jobs/{job_id}/confirm": STANDARD_WRITE,
    "POST /jobs/{job_id}/quotes": STANDARD_WRITE,
    "POST /jobs/{job_id}/quotes/{quote_id}/accept": STANDARD_WRITE,
    "POST /kyc/resubmit": SENSITIVE_WRITE,
    "POST /kyc/submit": SENSITIVE_WRITE,
    "POST /kyc/{kyc_record_id}/approve": ADMIN_WRITE,
    "POST /kyc/{kyc_record_id}/reject": ADMIN_WRITE,
    "POST /kyc/{kyc_record_id}/request-resubmit": ADMIN_WRITE,
    "POST /listings/import": STANDARD_WRITE,
    "POST /listings/import/preview": STANDARD_WRITE,
    "POST /media/kyc-doc/sign": SENSITIVE_WRITE,
    "POST /media/sign": SENSITIVE_WRITE,
    "POST /merch/slots": ADMIN_WRITE,
    "POST /merch/slots/{slot_id}/draft": ADMIN_WRITE,
    "POST /merch/slots/{slot_id}/publish": ADMIN_WRITE,
    "POST /orders": PAYMENT_WRITE,
    "POST /orders/{order_id}/confirm-received": STANDARD_WRITE,
    "POST /orders/{order_id}/dispatch": PAYMENT_WRITE,
    "POST /orders/{order_id}/escrow": PAYMENT_WRITE,
    "POST /orders/{order_id}/evidence/sign": SENSITIVE_WRITE,
    "POST /orders/{order_id}/intervene": ADMIN_WRITE,
    "POST /orders/{order_id}/report-problem": STANDARD_WRITE,
    "POST /organiser/events": STANDARD_WRITE,
    "POST /organiser/events/{event_id}/cancel": STANDARD_WRITE,
    "POST /organiser/events/{event_id}/end": STANDARD_WRITE,
    "POST /organiser/events/{event_id}/publish": STANDARD_WRITE,
    "POST /organiser/events/{event_id}/ticket-types": STANDARD_WRITE,
    "POST /payments/card/session": PAYMENT_WRITE,
    "POST /payments/card/{payment_id}/verify": PAYMENT_WRITE,
    "POST /payments/retry": PAYMENT_WRITE,
    "POST /products/merge": ADMIN_WRITE,
    "PUT /products/{product_id}/relations": ADMIN_WRITE,
    "POST /quotes/{quote_id}/decline": STANDARD_WRITE,
    "POST /quotes/{quote_id}/withdraw": STANDARD_WRITE,
    "POST /refunds/execute": PAYMENT_WRITE,
    "POST /returns": STANDARD_WRITE,
    "POST /returns/{return_id}/respond": STANDARD_WRITE,
    "POST /reviews": STANDARD_WRITE,
    "POST /reviews/{review_id}/reply": STANDARD_WRITE,
    "POST /support/send": ADMIN_WRITE,
    "POST /tickets/checkout": PAYMENT_WRITE,
    "POST /tickets/rsvp": PAYMENT_WRITE,
    "POST /tickets/transfers/{transfer_id}/cancel": STANDARD_WRITE,
    "POST /tickets/transfers/{transfer_id}/claim": STANDARD_WRITE,
    "POST /tickets/verify": SENSITIVE_WRITE,
    "POST /tickets/verify/batch": SENSITIVE_WRITE,
    "POST /tickets/{ticket_id}/transfer": STANDARD_WRITE,
    "POST /vendor/listings": STANDARD_WRITE,
    "POST /vendor/listings/{listing_id}/images": STANDARD_WRITE,
    "POST /vendor/listings/{listing_id}/pause": STANDARD_WRITE,
    "POST /vendor/listings/{listing_id}/unpause": STANDARD_WRITE,
    "POST /vendor/orders/{order_id}/cod/confirm-collection": PAYMENT_WRITE,
    "POST /vendor/orders/{order_id}/cod/refuse-collection": PAYMENT_WRITE,
    "POST /vendor/orders/{order_id}/confirm": STANDARD_WRITE,
    "POST /vendor/orders/{order_id}/pack": STANDARD_WRITE,
    "POST /vendor/orders/{order_id}/ready-for-pickup": STANDARD_WRITE,
    "POST /vendor/orders/{order_id}/reject": STANDARD_WRITE,
    "POST /vendor/orders/{order_id}/ship": STANDARD_WRITE,
    "POST /vendor/payouts/method": PAYMENT_WRITE,
    "POST /vendor/pickup/verify": SENSITIVE_WRITE,
    "POST /vendor/services": STANDARD_WRITE,
    "PUT /admin/translations/overrides": ADMIN_WRITE,
    "PUT /organiser/ticket-types/{ticket_type_id}/allocations": STANDARD_WRITE,
    "PUT /organiser/ticket-types/{ticket_type_id}/early-bird": STANDARD_WRITE,
    "PUT /organiser/ticket-types/{ticket_type_id}/price-tiers": STANDARD_WRITE,
}


class UncoveredMutatingRoutesError(RuntimeError):
    """Raised at startup when a mutating route has no rate-limit policy."""


def route_id(method: str, path: str) -> str:
    """Stable registry key for a route: ``"{METHOD} {path}"``."""
    return f"{method.upper()} {path}"


def _iter_routes(routes: object) -> Iterator[Route]:
    """Recursively yield concrete :class:`Route` objects.

    FastAPI (>=0.139) wraps ``include_router`` results in an opaque
    ``_IncludedRouter`` exposing ``original_router``; we recurse through both
    that and any nested ``routes`` collection so no mounted route is missed.
    """
    if not isinstance(routes, (list, tuple)):
        return
    for route in routes:
        if isinstance(route, Route):
            yield route
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_routes(getattr(original, "routes", None))
            continue
        nested = getattr(route, "routes", None)
        if nested is not None:
            yield from _iter_routes(nested)


def iter_mutating_route_ids(app: object) -> set[str]:
    """Return the route id of every mutating (POST/PUT/PATCH/DELETE) route."""
    ids: set[str] = set()
    routes = getattr(app, "routes", None)
    for route in _iter_routes(routes):
        methods = route.methods or set()
        for method in methods & MUTATING_METHODS:
            ids.add(route_id(method, route.path))
    return ids


def policy_for(method: str, path: str) -> RateLimitPolicy | None:
    """Look up the declared policy for a route, or ``None`` if exempt/unknown.

    Intended for a shared enforcement dependency/middleware so enforcement can
    read the declarative registry instead of editing each router.
    """
    return POLICIES.get(route_id(method, path))


def assert_all_mutating_routes_covered(app: object) -> None:
    """Fail loudly if any mutating route lacks a declared rate-limit policy.

    Called once at startup. Every POST/PUT/PATCH/DELETE route in the live route
    table must either appear in :data:`POLICIES` or be in the explicit
    :data:`EXEMPT_ROUTE_IDS` allowlist. Raises
    :class:`UncoveredMutatingRoutesError` listing every gap.
    """
    mutating = iter_mutating_route_ids(app)
    covered = set(POLICIES) | EXEMPT_ROUTE_IDS
    uncovered = sorted(mutating - covered)
    if uncovered:
        listed = "\n  - ".join(uncovered)
        raise UncoveredMutatingRoutesError(
            "Mutating routes without a rate-limit policy (add to POLICIES in "
            "app/core/ratelimit_policies.py, or to the documented "
            f"EXEMPT_ROUTE_IDS allowlist):\n  - {listed}"
        )
