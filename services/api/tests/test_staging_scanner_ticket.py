"""Safety contract for the canonical free-RSVP scanner certification ticket."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from app.errors import AppError
from app.services.tickets import purchase
from app.services.tickets.qr import verify_pin
from app.staging import scanner_ticket
from app.staging.scanner_ticket import (
    SCANNER_RSVP_IDEMPOTENCY_KEY,
    build_scanner_rsvp_cleanup_sql,
    issue_scanner_certification_ticket,
)
from app.staging.synthetic_contract import event_fixture
from app.staging.ticket_credentials import certification_ticket_credentials

SERVICE_ROLE_A = "staging-scanner-service-role-a"
SERVICE_ROLE_B = "staging-scanner-service-role-b"


@pytest.fixture(autouse=True)
def service_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_ROLE_A)


def test_canonical_event_has_a_zero_price_free_rsvp_scanner_type() -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    ticket = event.tickets[0]
    ticket_type = next(
        item for item in event.ticket_types if item.ticket_type_id == ticket.ticket_type_id
    )
    assert ticket_type.kind == "free_rsvp"
    assert ticket_type.price_ngwee == 0


def test_paid_purchase_type_remains_separate() -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    paid = [item for item in event.ticket_types if item.kind != "free_rsvp"]
    assert [(item.kind, item.price_ngwee) for item in paid] == [("fixed", 15000)]
    assert event.tickets[0].ticket_type_id not in {item.ticket_type_id for item in paid}


def test_certification_credentials_are_deterministic() -> None:
    assert certification_ticket_credentials() == certification_ticket_credentials()


def test_certification_credentials_are_environment_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = certification_ticket_credentials()[0]
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_ROLE_B)
    second = certification_ticket_credentials()[0]
    assert first.ticket_id == second.ticket_id
    assert (first.pin, first.qr_secret, first.pin_hash) != (
        second.pin,
        second.qr_secret,
        second.pin_hash,
    )


def test_certification_pin_uses_the_production_verifier() -> None:
    credential = certification_ticket_credentials()[0]
    assert verify_pin(
        pin=credential.pin,
        ticket_id=credential.ticket_id,
        pin_hash=credential.pin_hash,
    )


def test_credential_repr_redacts_the_pin() -> None:
    credential = certification_ticket_credentials()[0]
    assert credential.pin not in repr(credential)
    assert "<redacted>" in repr(credential)


def test_cleanup_follows_restrict_fk_order() -> None:
    sql = build_scanner_rsvp_cleanup_sql()
    assert sql.index("DELETE FROM public.event_checkin_overrides") < sql.index(
        "DELETE FROM public.tickets"
    )
    assert sql.index("DELETE FROM public.tickets") < sql.index(
        "DELETE FROM public.order_items"
    )
    assert sql.index("DELETE FROM public.order_items") < sql.index(
        "DELETE FROM public.orders"
    )
    assert sql.index("DELETE FROM public.orders") < sql.index(
        "DELETE FROM public.checkout_groups"
    )


def test_cleanup_is_scoped_to_canonical_identity() -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    sql = build_scanner_rsvp_cleanup_sql()
    assert event.tickets[0].ticket_id in sql
    assert SCANNER_RSVP_IDEMPOTENCY_KEY in sql
    assert "LIKE" not in sql


def _rsvp_outcome() -> SimpleNamespace:
    return SimpleNamespace(
        ticket_ids=("01000000-0000-4000-8000-000000000001",),
        order_item_id="01000000-0000-4000-8000-000000000002",
        order_id="01000000-0000-4000-8000-000000000003",
        checkout_group_id="01000000-0000-4000-8000-000000000004",
    )


def test_issuer_calls_real_rsvp_with_the_free_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    sql_calls: list[str] = []

    def fake_rsvp(_client: Any, **kwargs: Any) -> SimpleNamespace:
        calls.update(kwargs)
        return _rsvp_outcome()

    def fake_sql(sql: str) -> SimpleNamespace:
        sql_calls.append(sql)
        return SimpleNamespace(ok=True, rows=["1"] if "SELECT count(*)" in sql else [])

    monkeypatch.setattr(scanner_ticket, "rsvp", fake_rsvp)
    monkeypatch.setattr(scanner_ticket, "run_sql_script", fake_sql)

    credential = issue_scanner_certification_ticket(object())
    event = event_fixture("EVENT_LAUNCH_EXPO")
    ticket = event.tickets[0]
    assert calls == {
        "customer_id": "a1000000-0000-4000-8000-000000000001",
        "instance_id": event.instance_id,
        "ticket_type_id": ticket.ticket_type_id,
        "qty": 1,
    }
    assert credential.ticket_id == ticket.ticket_id
    assert len(sql_calls) == 2


def test_canonicalisation_keeps_free_order_semantics_and_no_payment_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql_calls: list[str] = []
    monkeypatch.setattr(scanner_ticket, "rsvp", lambda *_args, **_kwargs: _rsvp_outcome())

    def fake_sql(sql: str) -> SimpleNamespace:
        sql_calls.append(sql)
        return SimpleNamespace(ok=True, rows=["1"] if "SELECT count(*)" in sql else [])

    monkeypatch.setattr(scanner_ticket, "run_sql_script", fake_sql)
    issue_scanner_certification_ticket(object())
    finalise = sql_calls[-1]
    assert "tt.kind = 'free_rsvp'" in finalise
    assert "tt.price_ngwee = 0" in finalise
    assert "NOT EXISTS" in finalise and "public.payments" in finalise
    assert "INSERT INTO public.payments" not in finalise
    assert "UPDATE public.payments" not in finalise


def test_issuer_refuses_a_paid_scanner_fixture_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    paid_type = event.ticket_types[0]
    broken_ticket = replace(event.tickets[0], ticket_type_id=paid_type.ticket_type_id)
    broken_event = replace(event, tickets=(broken_ticket,))
    monkeypatch.setattr(scanner_ticket, "event_fixture", lambda _key: broken_event)
    monkeypatch.setattr(
        scanner_ticket,
        "run_sql_script",
        lambda _sql: pytest.fail("paid fixture must fail before SQL"),
    )
    with pytest.raises(RuntimeError, match="zero-price free RSVP"):
        issue_scanner_certification_ticket(object())


def test_failed_canonicalisation_removes_the_partial_rsvp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql_calls: list[str] = []
    monkeypatch.setattr(scanner_ticket, "rsvp", lambda *_args, **_kwargs: _rsvp_outcome())

    def fake_sql(sql: str) -> SimpleNamespace:
        sql_calls.append(sql)
        if len(sql_calls) == 1:
            return SimpleNamespace(ok=True, rows=[], error=None)
        if len(sql_calls) == 2:
            return SimpleNamespace(ok=True, rows=["0"], error=None)
        return SimpleNamespace(ok=True, rows=[], error=None)

    monkeypatch.setattr(scanner_ticket, "run_sql_script", fake_sql)
    with pytest.raises(RuntimeError, match="canonicalisation failed"):
        issue_scanner_certification_ticket(object())
    assert len(sql_calls) == 3
    assert _rsvp_outcome().checkout_group_id in sql_calls[-1]
    assert _rsvp_outcome().ticket_ids[0] in sql_calls[-1]


def test_paid_ticket_type_cannot_enter_the_rsvp_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    paid_type = event.ticket_types[0]
    monkeypatch.setattr(
        purchase,
        "_load_ticket_context",
        lambda *_args, **_kwargs: {
            "event": {"id": event.event_id, "visibility": "public"},
            "ticket_type": {
                "kind": paid_type.kind,
                "name": paid_type.name,
                "price_ngwee": paid_type.price_ngwee,
            },
            "organiser_vendor_id": "b1000000-0000-4000-8000-000000000004",
        },
    )
    with pytest.raises(AppError) as exc:
        purchase.rsvp(
            object(),
            customer_id="a1000000-0000-4000-8000-000000000001",
            instance_id=event.instance_id,
            ticket_type_id=paid_type.ticket_type_id,
        )
    assert exc.value.code == "tickets.paid_use_checkout"
