"""The canonical staging scanner ticket, driven against a real database.

This module exists because of a live staging failure: the organiser scanner
reached `POST /tickets/verify` and got `409 ticket_unpaid_hold`. The API was
right — the canonical fixture wrote its scanner ticket straight into
`public.tickets`, so it had no `order_item_id` and no order had ever issued it.

What is proven here, end to end on a migrated schema:

* the seeded scanner ticket carries a real `order_item_id`, because the seeder
  drives `services/tickets/purchase.py::rsvp()` rather than writing a row;
* a real `verify_and_check_in_ticket()` accepts it on the minted PIN, and
  rejects a second attempt with `ticket_already_checked_in`;
* the preserved paid fixture is still an unpaid hold and still gets
  `ticket_unpaid_hold` — with the CORRECT PIN, so the refusal is about payment
  and nothing else;
* nothing in the setup writes a `payments` row, successful or otherwise;
* cleanup removes the whole spine and a reseed hands back a fresh, un-scanned
  scanner ticket.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest
from app.errors import AppError
from app.routers.ticket_verify import verify_and_check_in_ticket
from app.services.tickets.qr import extract_pin_for_holder
from app.staging.event_scanner import (
    ScannerTicket,
    apply_rsvp_scanner_ticket,
    scanner_ticket_fixture,
)
from app.staging.seed_sql import build_cleanup_sql, build_seed_sql, parse_verification
from app.staging.seed_sql import verification_queries as seed_verification_queries
from app.staging.synthetic_contract import (
    PERSONAS,
    event_fixture,
    persona_by_key,
    scanner_ticket_type,
)
from app.staging.ticket_credentials import mint_ticket_credentials
from tests.rls.conftest import PgConn, apply_migrations, resolve_db_url, schema_ready

EVENT = event_fixture("EVENT_LAUNCH_EXPO")
ORGANISER_VENDOR_ID = persona_by_key(EVENT.organiser_key).vendor_id or ""
UNPAID_HOLD_TICKET_ID = EVENT.tickets[0].ticket_id


class _ServiceWrapper:
    """Stand-in for the Supabase service client.

    `rsvp()` only reaches `.client` for a PRIVATE event's access proof, and the
    canonical event is public, so any use of it here is a fixture bug worth
    failing loudly on.
    """

    def __init__(self) -> None:
        class _Client:
            def table(self, name: str) -> Any:
                raise RuntimeError(f"unexpected Supabase table access: {name}")

        self.client = _Client()


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _ensure_auth_personas(conn: PgConn) -> None:
    """Stand in for the Auth Admin API the real seeder calls first.

    `build_seed_sql()` only writes public.* rows; every one of them FK-references
    auth.users, which GoTrue owns on a real project.
    """
    for persona in PERSONAS:
        result = conn.run(
            "INSERT INTO auth.users (id, email, aud, role) VALUES "
            f"('{persona.user_id}', '{persona.email}', 'authenticated', 'authenticated') "
            "ON CONFLICT (id) DO NOTHING;"
        )
        assert result.ok, result.error


def _seed(conn: PgConn) -> None:
    _ensure_auth_personas(conn)
    result = conn.run(build_seed_sql(mint_ticket_credentials()))
    assert result.ok, result.error


def _cleanup(conn: PgConn) -> None:
    result = conn.run(build_cleanup_sql())
    assert result.ok, result.error


def _scalar(conn: PgConn, sql: str) -> str:
    result = conn.run(sql)
    assert result.ok, result.error
    return result.rows[0] if result.rows else ""


@pytest.fixture
def seeded_scanner(
    db: PgConn, db_url_env: None
) -> Generator[tuple[PgConn, ScannerTicket], None, None]:
    """A clean canonical fixture plus the run's scanner ticket."""
    _cleanup(db)
    _seed(db)
    scanner = apply_rsvp_scanner_ticket(_ServiceWrapper())
    yield db, scanner
    _cleanup(db)


# ── The repaired fixture ──────────────────────────────────────────────────


def test_scanner_ticket_carries_a_real_order_item_id(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    """The exact defect, inverted: this ticket was issued BY an order item."""
    conn, scanner = seeded_scanner
    row = _scalar(
        conn,
        "SELECT coalesce(t.order_item_id::text, '') || '|' || t.status || '|' || "
        "coalesce(t.checked_in_at::text, '') || '|' || tt.kind || '|' || e.status "
        "FROM public.tickets t "
        "JOIN public.ticket_types tt ON tt.id = t.ticket_type_id "
        "JOIN public.event_instances ei ON ei.id = t.instance_id "
        "JOIN public.events e ON e.id = ei.event_id "
        f"WHERE t.id = '{scanner.ticket_id}';",
    )
    order_item_id, status, checked_in_at, kind, event_status = row.split("|")
    assert order_item_id == scanner.order_item_id
    assert status == "issued"
    assert checked_in_at == ""
    assert kind == "free_rsvp"
    assert event_status == "published"


def test_scanner_order_item_is_a_real_ticket_line_on_a_completed_order(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    conn, scanner = seeded_scanner
    row = _scalar(
        conn,
        "SELECT oi.item_kind || '|' || oi.qty::text || '|' || o.status || '|' || "
        "cg.status || '|' || oit.instance_id::text "
        "FROM public.order_items oi "
        "JOIN public.orders o ON o.id = oi.order_id "
        "JOIN public.checkout_groups cg ON cg.id = o.checkout_group_id "
        "JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id "
        f"WHERE oi.id = '{scanner.order_item_id}';",
    )
    item_kind, qty, order_status, group_status, instance_id = row.split("|")
    assert item_kind == "ticket"
    assert qty == "1"
    # rsvp() completes the spine outright — there is nothing left to pay.
    assert order_status == "completed"
    assert group_status == "completed"
    assert instance_id == EVENT.instance_id


def test_setup_creates_no_payment_row_for_the_synthetic_fixture(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    """No fabricated payment success — no payment record of any status.

    The free-RSVP path is legitimate precisely because it never claims money
    changed hands. A `payments` row here, successful or not, would mean the
    fixture had invented one. Scoped to the synthetic personas' checkout groups
    rather than the whole table, so an unrelated module's fixtures sharing this
    test database cannot make this pass or fail for the wrong reason.
    """
    conn, scanner = seeded_scanner
    synthetic_users = ", ".join(f"'{p.user_id}'" for p in PERSONAS)
    assert (
        _scalar(
            conn,
            "SELECT count(*)::text FROM public.payments p "
            "JOIN public.checkout_groups cg ON cg.id = p.checkout_group_id "
            f"WHERE cg.customer_id IN ({synthetic_users});",
        )
        == "0"
    )
    assert (
        _scalar(
            conn,
            "SELECT count(*)::text FROM public.payments "
            f"WHERE checkout_group_id = '{scanner.checkout_group_id}';",
        )
        == "0"
    )


def test_seed_verification_passes_against_the_live_fixture(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    """The seeder's own gate, run against a real seeded database."""
    conn, _ = seeded_scanner
    results: dict[str, list[str]] = {}
    for key, sql in seed_verification_queries().items():
        result = conn.run(sql)
        assert result.ok, f"{key}: {result.error}"
        results[key] = result.rows
    parse_verification(results)
    assert results["scanner_ticket_checkinable"] == ["1"]
    assert results["unpaid_paid_holds"] == ["1"]


# ── Real verification ─────────────────────────────────────────────────────


def test_real_verify_checks_in_the_scanner_ticket_then_rejects_a_replay(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    """The organiser scanner journey, through the production endpoint's code."""
    _, scanner = seeded_scanner
    result = verify_and_check_in_ticket(
        ticket_id=scanner.ticket_id,
        vendor_id=ORGANISER_VENDOR_ID,
        pin=scanner.pin,
        expected_event_id=EVENT.event_id,
        expected_instance_id=EVENT.instance_id,
    )
    assert result.from_status == "issued"
    assert result.to_status == "checked_in"

    with pytest.raises(AppError) as exc:
        verify_and_check_in_ticket(
            ticket_id=scanner.ticket_id,
            vendor_id=ORGANISER_VENDOR_ID,
            pin=scanner.pin,
            expected_event_id=EVENT.event_id,
            expected_instance_id=EVENT.instance_id,
        )
    assert exc.value.code == "ticket_already_checked_in"
    assert exc.value.http_status == 409


def test_minted_pin_is_the_one_the_service_sealed(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    """No credential is written over the service's own.

    `_link_claimed_tickets` seals the PIN; the seeder reads it back through
    `extract_pin_for_holder` — the same call the wallet endpoint serves to the
    holder — so the scanner is driven with a PIN a real attendee would see.
    """
    conn, scanner = seeded_scanner
    pin_hash = _scalar(
        conn,
        f"SELECT pin_hash FROM public.tickets WHERE id = '{scanner.ticket_id}';",
    )
    assert extract_pin_for_holder(pin_hash, ticket_id=scanner.ticket_id) == scanner.pin


# ── The safety rule this repair must not weaken ───────────────────────────


def test_unpaid_paid_hold_still_fails_with_ticket_unpaid_hold(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    """The preserved GA fixture is refused — on payment, not on credentials.

    The PIN handed in below is the CORRECT one for that ticket, minted by the
    same sealing path, and the organiser is the real one. The only thing wrong
    with it is that no order item issued it, which is exactly the rule
    `_assert_paid_ticket` enforces.
    """
    conn, _ = seeded_scanner
    hold_pin_hash = _scalar(
        conn,
        f"SELECT pin_hash FROM public.tickets WHERE id = '{UNPAID_HOLD_TICKET_ID}';",
    )
    hold_pin = extract_pin_for_holder(hold_pin_hash, ticket_id=UNPAID_HOLD_TICKET_ID)
    assert hold_pin, "the static hold must carry a readable PIN to be a fair control"
    assert (
        _scalar(
            conn,
            "SELECT coalesce(order_item_id::text, '') FROM public.tickets "
            f"WHERE id = '{UNPAID_HOLD_TICKET_ID}';",
        )
        == ""
    )

    with pytest.raises(AppError) as exc:
        verify_and_check_in_ticket(
            ticket_id=UNPAID_HOLD_TICKET_ID,
            vendor_id=ORGANISER_VENDOR_ID,
            pin=hold_pin,
        )
    assert exc.value.code == "ticket_unpaid_hold"
    assert exc.value.http_status == 409
    # Refused AND untouched.
    assert (
        _scalar(
            conn,
            "SELECT status || '|' || coalesce(checked_in_at::text, '') "
            f"FROM public.tickets WHERE id = '{UNPAID_HOLD_TICKET_ID}';",
        )
        == "issued|"
    )


def test_paid_general_admission_fixture_is_still_seeded(
    seeded_scanner: tuple[PgConn, ScannerTicket],
) -> None:
    conn, _ = seeded_scanner
    paid_row = _scalar(
        conn,
        "SELECT kind || '|' || price_ngwee::text || '|' || name "
        "FROM public.ticket_types "
        "WHERE id = 'e3000000-0000-4000-8000-000000000001';",
    )
    assert paid_row == "fixed|15000|General admission"


# ── Cleanup and replay ────────────────────────────────────────────────────


def test_cleanup_removes_the_scanner_ticket_and_its_whole_order_spine(
    db: PgConn, db_url_env: None
) -> None:
    _cleanup(db)
    _seed(db)
    scanner = apply_rsvp_scanner_ticket(_ServiceWrapper())

    _cleanup(db)

    for sql in (
        f"SELECT count(*)::text FROM public.tickets WHERE id = '{scanner.ticket_id}';",
        "SELECT count(*)::text FROM public.order_items WHERE id = "
        f"'{scanner.order_item_id}';",
        f"SELECT count(*)::text FROM public.orders WHERE id = '{scanner.order_id}';",
        "SELECT count(*)::text FROM public.checkout_groups WHERE id = "
        f"'{scanner.checkout_group_id}';",
        "SELECT count(*)::text FROM public.order_item_tickets WHERE instance_id = "
        f"'{EVENT.instance_id}';",
        f"SELECT count(*)::text FROM public.events WHERE id = '{EVENT.event_id}';",
        "SELECT count(*)::text FROM public.ticket_types WHERE id = "
        f"'{scanner_ticket_type(EVENT).ticket_type_id}';",
    ):
        assert _scalar(db, sql) == "0", sql


def test_cleanup_is_replay_safe_and_reseed_gives_a_fresh_unscanned_ticket(
    db: PgConn, db_url_env: None
) -> None:
    """Run it twice: the second run must look exactly like the first."""
    _cleanup(db)
    _seed(db)
    first = apply_rsvp_scanner_ticket(_ServiceWrapper())
    verify_and_check_in_ticket(
        ticket_id=first.ticket_id,
        vendor_id=ORGANISER_VENDOR_ID,
        pin=first.pin,
    )
    assert (
        _scalar(
            db,
            f"SELECT status FROM public.tickets WHERE id = '{first.ticket_id}';",
        )
        == "checked_in"
    )

    _cleanup(db)
    _seed(db)
    second = apply_rsvp_scanner_ticket(_ServiceWrapper())

    assert second.replayed is False
    assert second.ticket_id != first.ticket_id
    row = _scalar(
        db,
        "SELECT status || '|' || coalesce(checked_in_at::text, '') || '|' || "
        "coalesce(order_item_id::text, '') FROM public.tickets "
        f"WHERE id = '{second.ticket_id}';",
    )
    status, checked_in_at, order_item_id = row.split("|")
    assert (status, checked_in_at) == ("issued", "")
    assert order_item_id == second.order_item_id
    # A fresh ticket must be checkable again, or the E2E's first scan inverts.
    assert (
        verify_and_check_in_ticket(
            ticket_id=second.ticket_id,
            vendor_id=ORGANISER_VENDOR_ID,
            pin=second.pin,
        ).to_status
        == "checked_in"
    )
    _cleanup(db)


def test_reapply_without_cleanup_replays_the_same_ticket_unscanned(
    db: PgConn, db_url_env: None
) -> None:
    """A second --apply must not mint a second scanner ticket.

    Two live scanner tickets would drain the lane's allocation and leave the
    spec able to pick the wrong one; a still-checked-in one would invert the
    duplicate-reject assertion on the next run.
    """
    _cleanup(db)
    _seed(db)
    first = apply_rsvp_scanner_ticket(_ServiceWrapper())
    verify_and_check_in_ticket(
        ticket_id=first.ticket_id,
        vendor_id=ORGANISER_VENDOR_ID,
        pin=first.pin,
    )

    _seed(db)
    second = apply_rsvp_scanner_ticket(_ServiceWrapper())

    assert second.replayed is True
    assert second.ticket_id == first.ticket_id
    assert second.order_item_id == first.order_item_id
    # Replay restores the SCAN, never the payment linkage.
    assert (
        _scalar(
            db,
            "SELECT status || '|' || coalesce(checked_in_at::text, '') || '|' || "
            f"coalesce(order_item_id::text, '') FROM public.tickets "
            f"WHERE id = '{second.ticket_id}';",
        )
        == f"issued||{first.order_item_id}"
    )
    assert (
        _scalar(
            db,
            "SELECT count(*)::text FROM public.tickets t "
            "JOIN public.ticket_types tt ON tt.id = t.ticket_type_id "
            f"WHERE t.instance_id = '{EVENT.instance_id}' "
            "AND tt.kind = 'free_rsvp' AND t.status <> 'void';",
        )
        == "1"
    )
    _cleanup(db)


def test_scanner_setup_never_links_a_paid_ticket(
    db: PgConn, db_url_env: None
) -> None:
    """Whatever else the seeder does, it must not hand-link the paid lane."""
    _cleanup(db)
    _seed(db)
    apply_rsvp_scanner_ticket(_ServiceWrapper())
    assert (
        _scalar(
            db,
            "SELECT count(*)::text FROM public.tickets t "
            "JOIN public.ticket_types tt ON tt.id = t.ticket_type_id "
            f"WHERE t.instance_id = '{EVENT.instance_id}' "
            "AND tt.kind <> 'free_rsvp' AND t.order_item_id IS NOT NULL;",
        )
        == "0"
    )
    _cleanup(db)


def test_scanner_fixture_matches_the_contract_lane(db: PgConn, db_url_env: None) -> None:
    fixture = scanner_ticket_fixture()
    assert fixture.ticket_type.ticket_type_id == scanner_ticket_type(EVENT).ticket_type_id
    assert fixture.event.event_id == EVENT.event_id
