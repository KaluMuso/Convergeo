"""Full RLS isolation matrix: every public table x persona x verb."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest
from tests.rls.conftest import (
    VERBS,
    Outcome,
    Persona,
    PgConn,
    RoleSession,
    Verb,
)

# ---------------------------------------------------------------------------
# Expectation builders
# ---------------------------------------------------------------------------

PersonaExpectations = dict[Persona, dict[Verb, Outcome]]
TableExpectations = dict[str, PersonaExpectations]


def deny_all() -> dict[Verb, Outcome]:
    return {verb: "deny" for verb in VERBS}


def select_only() -> dict[Verb, Outcome]:
    return {"select": "permit", "insert": "deny", "update": "deny", "delete": "deny"}


def all_permit() -> dict[Verb, Outcome]:
    return {verb: "permit" for verb in VERBS}


def public_read_admin_write() -> PersonaExpectations:
    return {
        Persona.ANON: select_only(),
        Persona.CUSTOMER: select_only(),
        Persona.OTHER_CUSTOMER: select_only(),
        Persona.VENDOR: select_only(),
        Persona.OTHER_VENDOR: select_only(),
        Persona.ADMIN: all_permit(),
    }


def service_role_only() -> PersonaExpectations:
    """Tables with GRANT but zero client policies — SELECT returns 0 rows."""
    empty_read = select_only()
    return {persona: empty_read.copy() for persona in Persona}


def client_invisible() -> PersonaExpectations:
    """No GRANT to client roles — permission denied on all verbs."""
    denied = deny_all()
    return {persona: denied.copy() for persona in Persona}


def admin_config_table() -> PersonaExpectations:
    read = select_only()
    return {
        Persona.ANON: deny_all(),
        Persona.CUSTOMER: read,
        Persona.OTHER_CUSTOMER: read,
        Persona.VENDOR: read,
        Persona.OTHER_VENDOR: read,
        Persona.ADMIN: all_permit(),
    }


def admin_read_write() -> PersonaExpectations:
    write: dict[Verb, Outcome] = {
        "select": "permit",
        "insert": "deny",
        "update": "deny",
        "delete": "deny",
    }
    admin = all_permit()
    return {
        Persona.ANON: write,
        Persona.CUSTOMER: write,
        Persona.OTHER_CUSTOMER: write,
        Persona.VENDOR: write,
        Persona.OTHER_VENDOR: write,
        Persona.ADMIN: admin,
    }


# ruff: noqa: E501
EXPECTATIONS: TableExpectations = {
    "addresses": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "ask_cache": client_invisible(),
    "ask_spend_monthly": {
        Persona.ANON: deny_all(),
        Persona.CUSTOMER: select_only(),
        Persona.OTHER_CUSTOMER: select_only(),
        Persona.VENDOR: select_only(),
        Persona.OTHER_VENDOR: select_only(),
        Persona.ADMIN: select_only(),
    },
    "ask_usage": {
        Persona.ANON: deny_all(),
        Persona.CUSTOMER: select_only(),
        Persona.OTHER_CUSTOMER: select_only(),
        Persona.VENDOR: select_only(),
        Persona.OTHER_VENDOR: select_only(),
        Persona.ADMIN: select_only(),
    },
    "audit_log": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.VENDOR: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_VENDOR: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.ADMIN: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
    },
    "cart_items": {
        # 0012 grants anon full DML for guest carts, scoped by the
        # `request.cart_guest_token` GUC. The matrix harness runs anon with no
        # guest token, so select/update/delete execute but RLS filters to zero
        # rows (secure no-op → classified "permit"); insert is denied because
        # the WITH CHECK guest_token match fails. Same shape as owner-scoped
        # tables like `addresses`.
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "carts": {
        # See cart_items above: anon guest-cart DML is granted but token-scoped,
        # so with no guest token select/update/delete are RLS-filtered no-ops
        # (permit) and insert is denied by the WITH CHECK.
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "categories": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "checkout_groups": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
    },
    "commission_rates": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "config_audit": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
    },
    "delivery_zones": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "disputes": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "event_instances": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "events": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "feature_flags": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "flags": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "funnel_events": {
        Persona.ANON: deny_all(),
        Persona.CUSTOMER: select_only(),
        Persona.OTHER_CUSTOMER: select_only(),
        Persona.VENDOR: select_only(),
        Persona.OTHER_VENDOR: select_only(),
        Persona.ADMIN: select_only(),
    },
    "invoice_counters": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "invoices": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "job_quotes": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "jobs": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "kyc_records": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "ledger_accounts": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "ledger_postings": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "ledger_transactions": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "listing_images": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "merch_slots": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "notification_outbox": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.VENDOR: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_VENDOR: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.ADMIN: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
    },
    "order_events": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "order_item_products": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "permit",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "order_item_services": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "permit",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "order_item_tickets": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "permit",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "order_items": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "orders": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "payments": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "payouts": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "platform_config": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "products": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "permit",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "permit",
            "update": "deny",
            "delete": "deny",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "permit",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "permit",
            "update": "deny",
            "delete": "deny",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "deny",
            "delete": "deny",
        },
    },
    "profiles": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "prohibited_categories": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "rate_counters": client_invisible(),
    "refunds": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "returns": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "reviews": {
        # NOTE: the insert probe uses `INSERT ... DEFAULT VALUES`, which cannot
        # satisfy reviews' data-dependent RLS WITH CHECK (needs a real owned,
        # delivered order_item). So non-admin inserts trip the policy ("denied");
        # admin passes the policy and instead hits NOT NULL (not a permission
        # error). This matches every other data-gated table (addresses, disputes,
        # returns, flags). Legitimate-insert authz is proven by the verified-
        # purchase pgTAP tests in 0007 + the cross-tenant tests below.
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "search_documents": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
    },
    "search_query_log": {
        # M06-P06: admin-read / service-role-write query analytics. Same shape as
        # funnel_events — authenticated gets a SELECT grant + admin-only RLS policy
        # (non-admins execute but see zero rows → permit), no client insert/update/
        # delete grant (→ deny), and anon has no grant at all (→ deny_all).
        Persona.ANON: deny_all(),
        Persona.CUSTOMER: select_only(),
        Persona.OTHER_CUSTOMER: select_only(),
        Persona.VENDOR: select_only(),
        Persona.OTHER_VENDOR: select_only(),
        Persona.ADMIN: select_only(),
    },
    "services": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "stock_reservations": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
    },
    "synonyms": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "ticket_transfers": {
        # M10-P07: transfer-to-friend. Only sender (from_user_id) and admin have a
        # SELECT policy; there is no insert/update/delete policy for `authenticated`
        # at all — initiate/cancel/claim are server-controlled transitions executed
        # with the service-role client (see app/routers/ticket_transfer.py). No
        # grant to anon at all, so anon is denied on every verb. Update/delete probes
        # use `WHERE false` (see _update_probe_sql/_probe_delete) so they succeed
        # trivially for any role with a table GRANT — same convention as tickets.
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
    },
    "ticket_types": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "tickets": {
        # Tickets are issued by the checkout flow (service-role), never inserted
        # directly by clients. The DEFAULT VALUES insert probe is denied for every
        # non-admin persona (no client insert path / data-dependent check); admin
        # passes RLS and hits NOT NULL (not a permission error). Same convention as
        # reviews/addresses/disputes/returns/flags.
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "user_roles": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
    },
    "vendor_listings": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "vendor_locations": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "vendor_quotas": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "vendors": {
        Persona.ANON: {
            "select": "permit",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
    "webhook_events": {
        Persona.ANON: {
            "select": "deny",
            "insert": "deny",
            "update": "deny",
            "delete": "deny",
        },
        Persona.CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_CUSTOMER: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.OTHER_VENDOR: {
            "select": "permit",
            "insert": "deny",
            "update": "permit",
            "delete": "permit",
        },
        Persona.ADMIN: {
            "select": "permit",
            "insert": "permit",
            "update": "permit",
            "delete": "permit",
        },
    },
}

MATRIX_SUMMARY: Counter[str] = Counter()


def _is_permission_denied(result: Any) -> bool:
    if result.ok:
        return False
    if result.sqlstate == "42501":
        return True
    err = (result.error or "").lower()
    return (
        "permission denied" in err
        or "row-level security" in err
        or "violates row-level security" in err
    )


def _probe_select(session: RoleSession, table: str) -> Any:
    return session.execute(f"SELECT 1 FROM public.{table} LIMIT 1")


def _probe_insert(session: RoleSession, table: str) -> Any:
    session.execute("SAVEPOINT rls_probe")
    result = session.execute(
        f"INSERT INTO public.{table} DEFAULT VALUES RETURNING 1"
    )
    session.execute("ROLLBACK TO SAVEPOINT rls_probe")
    return result


def _update_probe_sql(db: PgConn, table: str) -> str:
    col_result = db.run(
        f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '{table}'
          AND column_name IN (
            'updated_at', 'created_at', 'id', 'series', 'category_key', 'zone_key',
            'key', 'flag', 'tier', 'next_no', 'rate_bps', 'label', 'no'
          )
        ORDER BY CASE column_name
          WHEN 'updated_at' THEN 1
          WHEN 'created_at' THEN 2
          WHEN 'id' THEN 3
          ELSE 4
        END
        LIMIT 1
        """
    )
    if not col_result.ok or not col_result.rows:
        return f"UPDATE public.{table} SET id = id WHERE false"
    col = col_result.rows[0]
    return f"UPDATE public.{table} SET {col} = {col} WHERE false"


def _probe_update(session: RoleSession, table: str) -> Any:
    sql = _update_probe_sql(session.conn, table)
    return session.execute(sql)


def _probe_delete(session: RoleSession, table: str) -> Any:
    return session.execute(f"DELETE FROM public.{table} WHERE false")


def _run_verb(session: RoleSession, table: str, verb: Verb) -> Any:
    if verb == "select":
        return _probe_select(session, table)
    if verb == "insert":
        return _probe_insert(session, table)
    if verb == "update":
        return _probe_update(session, table)
    return _probe_delete(session, table)


def _tables_in_db(db: PgConn) -> list[str]:
    result = db.run(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    assert result.ok, result.error
    return result.rows


def matrix_params(db: PgConn) -> list[tuple[str, Persona, Verb]]:
    tables = _tables_in_db(db)
    params: list[tuple[str, Persona, Verb]] = []
    for table in tables:
        if table not in EXPECTATIONS:
            continue
        for persona in Persona:
            for verb in VERBS:
                params.append((table, persona, verb))
    return params


@pytest.fixture(scope="session")
def matrix_cases(db: PgConn) -> list[tuple[str, Persona, Verb]]:
    return matrix_params(db)


def test_matrix_cell(
    table: str,
    persona: Persona,
    verb: Verb,
    role_factory: Callable[[Persona], RoleSession],
    db: PgConn,
) -> None:
    """Parametrized via pytest_generate_tests."""
    if table not in _tables_in_db(db):
        pytest.skip(f"{table} not present in live schema")
    expected = EXPECTATIONS[table][persona][verb]
    session = role_factory(persona)
    result = _run_verb(session, table, verb)
    denied = _is_permission_denied(result)
    if expected == "permit":
        assert not denied, f"{table}/{persona}/{verb}: expected permit, got {result.error}"
        MATRIX_SUMMARY["allow"] += 1
    else:
        assert denied, f"{table}/{persona}/{verb}: expected deny, query succeeded"
        MATRIX_SUMMARY["deny"] += 1


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "table" in metafunc.fixturenames and "persona" in metafunc.fixturenames:
        cases = [
            (table, persona, verb)
            for table in sorted(EXPECTATIONS.keys())
            for persona in Persona
            for verb in VERBS
        ]
        ids = [f"{t}-{p}-{v}" for t, p, v in cases]
        metafunc.parametrize("table,persona,verb", cases, ids=ids)


def test_matrix_summary(db: PgConn, role_factory: Callable[[Persona], RoleSession]) -> None:
    """Emit allow/deny counts for the implementation report."""
    allow = 0
    deny = 0
    for table in _tables_in_db(db):
        if table not in EXPECTATIONS:
            continue
        for persona in Persona:
            for verb in VERBS:
                expected = EXPECTATIONS[table][persona][verb]
                session = role_factory(persona)
                result = _run_verb(session, table, verb)
                if expected == "permit":
                    assert not _is_permission_denied(result)
                    allow += 1
                else:
                    assert _is_permission_denied(result)
                    deny += 1
    print(f"\nMATRIX SUMMARY: allow={allow} deny={deny} total={allow + deny}")
    assert allow > 0
    assert deny > 0


# ---------------------------------------------------------------------------
# Cross-tenant headline denials
# ruff: noqa: E501
# ---------------------------------------------------------------------------


def test_cross_vendor_cannot_read_rival_draft_listing(
    as_other_vendor: RoleSession, fixture_ids: dict[str, Any], db: PgConn
) -> None:
    """Non-active listings are owner-only; rival vendors must not see drafts."""
    listing_id = fixture_ids["listings"]["phone_a"]
    db.run(
        "BEGIN; SET LOCAL role service_role; "
        f"UPDATE public.vendor_listings SET status = 'draft' WHERE id = '{listing_id}'; "
        "COMMIT;"
    )
    result = as_other_vendor.execute(
        f"SELECT count(*)::int FROM public.vendor_listings WHERE id = '{listing_id}'"
    )
    assert result.ok
    assert result.rows[0] == "0"
    db.run(
        "BEGIN; SET LOCAL role service_role; "
        f"UPDATE public.vendor_listings SET status = 'active' WHERE id = '{listing_id}'; "
        "COMMIT;"
    )


def test_cross_vendor_cannot_update_rival_listing(
    as_other_vendor: RoleSession, fixture_ids: dict[str, Any], db: PgConn
) -> None:
    listing_a = fixture_ids["listings"]["phone_a"]
    before = db.run(
        f"SELECT price_ngwee::text FROM public.vendor_listings WHERE id = '{listing_a}'"
    )
    result = as_other_vendor.execute(
        f"UPDATE public.vendor_listings SET price_ngwee = 1 WHERE id = '{listing_a}'"
    )
    assert result.ok
    after = db.run(
        f"SELECT price_ngwee::text FROM public.vendor_listings WHERE id = '{listing_a}'"
    )
    assert after.rows == before.rows
    assert after.rows[0] != "1"


def test_cross_vendor_cannot_read_rival_payout(as_other_vendor: RoleSession, fixture_ids: dict[str, Any]) -> None:
    payout_a = fixture_ids["payouts"]["vendor_a"]
    result = as_other_vendor.execute(
        f"SELECT count(*)::int FROM public.payouts WHERE id = '{payout_a}'"
    )
    assert result.ok
    assert result.rows[0] == "0"


def test_cross_vendor_cannot_read_rival_quote(as_vendor: RoleSession, fixture_ids: dict[str, Any]) -> None:
    quote_b = fixture_ids["job_quotes"]["quote_b"]
    result = as_vendor.execute(
        f"SELECT count(*)::int FROM public.job_quotes WHERE id = '{quote_b}'"
    )
    assert result.ok
    assert result.rows[0] == "0"


def test_cross_customer_cannot_read_orders(as_other_customer: RoleSession, fixture_ids: dict[str, Any]) -> None:
    order_a = fixture_ids["orders"]["paid"]
    result = as_other_customer.execute(
        f"SELECT count(*)::int FROM public.orders WHERE id = '{order_a}'"
    )
    assert result.ok
    assert result.rows[0] == "0"


def test_cross_customer_cannot_read_payments(as_other_customer: RoleSession, fixture_ids: dict[str, Any]) -> None:
    payment = fixture_ids["payments"]["paid"]
    result = as_other_customer.execute(
        f"SELECT count(*)::int FROM public.payments WHERE id = '{payment}'"
    )
    assert result.ok
    assert result.rows[0] == "0"


def test_cross_customer_cannot_read_invoices(as_other_customer: RoleSession, fixture_ids: dict[str, Any]) -> None:
    invoice = fixture_ids["invoices"]["paid"]
    result = as_other_customer.execute(
        f"SELECT count(*)::int FROM public.invoices WHERE id = '{invoice}'"
    )
    assert result.ok
    assert result.rows[0] == "0"


def test_cross_customer_cannot_read_addresses(as_other_customer: RoleSession, fixture_ids: dict[str, Any]) -> None:
    address = fixture_ids["addresses"]["customer_a_home"]
    result = as_other_customer.execute(
        f"SELECT count(*)::int FROM public.addresses WHERE id = '{address}'"
    )
    assert result.ok
    assert result.rows[0] == "0"


def test_service_role_only_tables_invisible(as_customer: RoleSession) -> None:
    for table in ("notification_outbox", "audit_log"):
        result = as_customer.execute(f"SELECT 1 FROM public.{table} LIMIT 1")
        assert _is_permission_denied(result), table
    for table in ("user_roles", "stock_reservations"):
        result = as_customer.execute(f"SELECT count(*)::int FROM public.{table}")
        assert result.ok
        assert result.rows[0] == "0", table


def test_forged_admin_without_db_role_denied(db: PgConn) -> None:
    """JWT alone does not grant admin — user_roles row required."""
    customer_uid = "11111111-1111-1111-1111-111111111111"
    claims = (
        f'{{"sub":"{customer_uid}","role":"authenticated",'
        f'"app_metadata":{{"role":"admin"}},"aal":"aal1"}}'
    )
    result = db.run(
        "BEGIN; SET LOCAL ROLE vergeo_rls_tester; SET LOCAL role authenticated; "
        f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{claims}', true); END $$; "
        "SELECT count(*)::int FROM public.ledger_accounts; COMMIT;"
    )
    assert result.ok
    assert result.rows[0] == "0"
