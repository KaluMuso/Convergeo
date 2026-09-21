"""Canonical event/ticket fixture, fixture versioning and scanner credentials.

Covers the Workstream B security contract: the seed must refuse a production
target before it mutates anything, the ticket PIN must be minted per run and
sealed through the REAL verification path, and nothing secret may leak into the
version hash, the generated TypeScript, or a repr/exception.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from app.core.env_guards import PROD_SUPABASE_PROJECT_REF, StagingIsolationError
from app.services.tickets.qr import verify_pin
from app.staging.event_scanner import ScannerTicket, scanner_ticket_fixture
from app.staging.seed_sql import (
    build_cleanup_sql,
    build_events_sql,
    build_seed_sql,
    parse_scanner_verification,
    parse_verification,
    verification_queries,
)
from app.staging.synthetic_contract import (
    EVENTS,
    SEED_PREFIX,
    STAGING_SUPABASE_PROJECT_REF,
    assert_contract_valid,
    canonical_contract_document,
    event_fixture,
    fixture_version,
    guard_seed_targets,
    paid_ticket_type,
    persona_by_key,
    scanner_ticket_type,
)
from app.staging.ticket_credentials import mint_ticket_credentials, primary_ticket_pin

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROLE_STUB = "staging-service-role-key-under-test"


@pytest.fixture
def service_role_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_ROLE_STUB)
    return SERVICE_ROLE_STUB


# ── Event fixture identity ────────────────────────────────────────────────


def test_event_fixture_exists_and_is_contract_valid() -> None:
    assert_contract_valid()
    event = event_fixture("EVENT_LAUNCH_EXPO")
    assert SEED_PREFIX in event.slug
    assert event.status == "published"
    assert event.ticket_types, "scanner journey needs a ticket type"
    assert event.tickets, "the unpaid-hold negative control must stay seeded"


def test_event_organiser_is_an_approved_synthetic_vendor() -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    organiser = persona_by_key(event.organiser_key)
    assert organiser.vendor_status == "active"
    assert organiser.user_role == "vendor"
    # The scanner reuses the vendor-sell identity rather than inventing a third.
    assert organiser.key == "APPROVED_VENDOR_A"


def test_seeded_unpaid_hold_starts_unscanned_and_stays_on_the_paid_lane() -> None:
    event = event_fixture("EVENT_LAUNCH_EXPO")
    assert any(t.status == "issued" for t in event.tickets)
    # Every statically seeded row belongs to the PAID lane. A static row on the
    # free_rsvp lane would be an unpaid hold impersonating the scanner ticket.
    scanner_type_id = scanner_ticket_type(event).ticket_type_id
    assert all(t.ticket_type_id != scanner_type_id for t in event.tickets)


def test_paid_general_admission_fixture_is_preserved() -> None:
    """The Lenco-gated purchase journey's subject must survive this repair."""
    event = event_fixture("EVENT_LAUNCH_EXPO")
    paid = paid_ticket_type(event)
    assert paid.ticket_type_id == "e3000000-0000-4000-8000-000000000001"
    assert (paid.name, paid.kind, paid.price_ngwee) == ("General admission", "fixed", 15000)
    assert (paid.qty_cap, paid.allocation) == (200, 200)
    hold = event.tickets[0]
    assert hold.ticket_id == "e4000000-0000-4000-8000-000000000001"
    assert hold.ticket_type_id == paid.ticket_type_id


def test_scanner_lane_is_a_zero_priced_free_rsvp_type() -> None:
    """The no-payment path is the only one rsvp() will accept.

    `purchase.rsvp()` raises `tickets.paid_use_checkout` for anything that is not
    `free_rsvp`, and the DB's own `ticket_types_free_rsvp_price_chk` pins a
    free_rsvp type to price zero. Both are why the scanner ticket can be issued
    without fabricating a payment.
    """
    event = event_fixture("EVENT_LAUNCH_EXPO")
    scanner = scanner_ticket_type(event)
    assert scanner.kind == "free_rsvp"
    assert scanner.price_ngwee == 0
    assert scanner.pass_kind == "instance"
    assert scanner.attendee_named is False
    assert scanner.allocation and scanner.allocation <= event.capacity
    assert scanner.qty_cap == scanner.allocation
    assert scanner.ticket_type_id != paid_ticket_type(event).ticket_type_id


def test_scanner_fixture_resolves_a_published_event_and_seeded_holder() -> None:
    fixture = scanner_ticket_fixture()
    assert fixture.event.status == "published"
    assert fixture.instance_id == fixture.event.instance_id
    assert fixture.ticket_type.kind == "free_rsvp"
    assert fixture.holder_user_id == persona_by_key("CUSTOMER_A").user_id


def test_contract_rejects_a_statically_seeded_ticket_on_the_scanner_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = EVENTS[0]
    scanner_type = scanner_ticket_type(event)
    smuggled = replace(event.tickets[0], ticket_type_id=scanner_type.ticket_type_id)
    broken = replace(event, tickets=(smuggled,))
    monkeypatch.setattr("app.staging.synthetic_contract.EVENTS", (broken,))
    with pytest.raises(StagingIsolationError, match="rsvp"):
        assert_contract_valid()


def test_contract_rejects_an_event_without_a_scanner_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = EVENTS[0]
    paid_only = replace(event, ticket_types=(paid_ticket_type(event),))
    monkeypatch.setattr("app.staging.synthetic_contract.EVENTS", (paid_only,))
    with pytest.raises(StagingIsolationError, match="free_rsvp"):
        assert_contract_valid()


def test_event_sql_is_created_and_cleaned_in_dependency_order() -> None:
    seed = build_seed_sql()
    assert "public.events" in seed
    assert "public.event_instances" in seed
    assert "public.ticket_types" in seed
    assert "public.tickets" in seed

    cleanup = build_cleanup_sql()
    # Children before parents, and events before the vendors/users they point at.
    assert cleanup.index("DELETE FROM public.tickets") < cleanup.index(
        "DELETE FROM public.event_instances"
    )
    assert cleanup.index("DELETE FROM public.event_instances") < cleanup.index(
        "DELETE FROM public.events"
    )
    assert cleanup.index("DELETE FROM public.events") < cleanup.index(
        "DELETE FROM public.vendors"
    )


def test_reseeding_restores_an_unscanned_ticket() -> None:
    # Idempotency that matters for the scanner: a re-run must clear checked_in_at
    # or the duplicate-reject assertion inverts on the second run.
    assert "checked_in_at = NULL" in build_events_sql()


def test_cleanup_removes_the_scanner_ticket_order_spine_in_fk_order() -> None:
    """Cleanup must dismantle the rsvp() spine, and in a legal order.

    order_item_tickets restrict-references ticket_types and event_instances, so
    a surviving ticket order makes the ticket-type/instance deletes fail
    outright; tickets.order_item_id references order_items with no ON DELETE
    action, so the order items cannot go first either.
    """
    cleanup = build_cleanup_sql()
    spine = cleanup.index("JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id")
    tickets = cleanup.index("DELETE FROM public.tickets")
    ticket_types = cleanup.index("DELETE FROM public.ticket_types")
    instances = cleanup.index("DELETE FROM public.event_instances")
    assert tickets < spine < ticket_types
    assert spine < instances


def test_cleanup_sweeps_the_orphaned_scanner_checkout_group() -> None:
    """rsvp() mints its own idempotency key, so the txn namespace cannot catch it.

    The sweep is bounded to synthetic personas AND to groups with nothing left
    pointing at them, so a group still carrying a payment or a stock hold is
    never force-deleted.
    """
    cleanup = build_cleanup_sql()
    sweep = cleanup.split("DELETE FROM public.checkout_groups cg", 1)[1].split(";", 1)[0]
    assert "cg.customer_id IN" in sweep
    for guarded in ("public.orders", "public.payments", "public.stock_reservations"):
        assert "NOT EXISTS" in sweep and guarded in sweep
    # Leaving it behind would make the profiles guard read it as a real order.
    profiles = cleanup.index("DELETE FROM public.profiles")
    assert cleanup.index("DELETE FROM public.checkout_groups cg") < profiles


def test_event_verification_queries_are_scoped_to_the_synthetic_prefix() -> None:
    queries = verification_queries()
    for key in (
        "event_published",
        "event_instances_scheduled",
        "event_ticket_types",
        "issued_tickets",
        "scanner_ticket_checkinable",
    ):
        assert SEED_PREFIX in queries[key], f"{key} must be prefix-scoped"


def _passing_verification() -> dict[str, list[str]]:
    """A results set every parse_verification() gate accepts."""
    return {
        "multiseller_count": ["2"],
        "multiseller_listings": ["2"],
        "location_stock_rows": ["2"],
        "oos_stock": ["0"],
        "wholesale_product_d": ["true"],
        "zero_price_guard": ["0"],
        "event_published": ["1"],
        "event_instances_scheduled": ["1"],
        "event_ticket_types": ["2"],
        "issued_tickets": ["2"],
        "scanner_ticket_checkinable": ["1"],
        "unpaid_paid_holds": ["1"],
    }


def test_event_verification_accepts_the_repaired_fixture_shape() -> None:
    parse_verification(_passing_verification())


def test_event_verification_rejects_a_missing_issued_ticket() -> None:
    results = _passing_verification() | {"issued_tickets": ["0"]}
    with pytest.raises(RuntimeError, match="unpaid-hold"):
        parse_verification(results)


def test_scanner_verification_rejects_a_scanner_ticket_without_an_order_item() -> None:
    """The exact S3 failure, caught at seed time instead of in the browser.

    A scanner ticket with no `order_item_id` is an unpaid hold, and
    `POST /tickets/verify` answers `ticket_unpaid_hold` for it. That answer is
    correct; the fixture was wrong. This gate makes the fixture fail loudly.
    """
    results = _passing_verification() | {"scanner_ticket_checkinable": ["0"]}
    with pytest.raises(RuntimeError, match="order_item_id"):
        parse_scanner_verification(results)


def test_static_contract_does_not_require_the_rsvp_issued_scanner_ticket() -> None:
    """`parse_verification()` covers build_seed_sql() and nothing more.

    Callers that apply the static SQL alone — `test_seed_staging.py` is one —
    must not be failed for a row only `app.staging.event_scanner` creates. The
    scanner gate lives in `parse_scanner_verification()` for exactly that
    reason; folding it back in would break every SQL-only caller.
    """
    parse_verification(_passing_verification() | {"scanner_ticket_checkinable": ["0"]})


def test_scanner_verification_accepts_a_linked_scanner_ticket() -> None:
    parse_scanner_verification(_passing_verification())


def test_event_verification_rejects_a_hand_linked_paid_hold() -> None:
    """Shortcutting the repair by linking the paid hold must fail the seed."""
    results = _passing_verification() | {"unpaid_paid_holds": ["0"]}
    with pytest.raises(RuntimeError, match="unpaid-hold"):
        parse_verification(results)


def test_contract_rejects_an_unapproved_event_organiser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = replace(EVENTS[0], organiser_key="PENDING_VENDOR")
    monkeypatch.setattr("app.staging.synthetic_contract.EVENTS", (broken,))
    with pytest.raises(StagingIsolationError, match="approved"):
        assert_contract_valid()


def test_contract_rejects_an_event_slug_without_the_seed_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = replace(EVENTS[0], slug="launch-expo")
    monkeypatch.setattr("app.staging.synthetic_contract.EVENTS", (broken,))
    with pytest.raises(StagingIsolationError, match="seed prefix"):
        assert_contract_valid()


# ── Production target refusal ─────────────────────────────────────────────


def test_seed_refuses_the_production_project_ref_before_mutating() -> None:
    with pytest.raises(StagingIsolationError):
        guard_seed_targets(
            supabase_url=f"https://{PROD_SUPABASE_PROJECT_REF}.supabase.co",
            db_url="",
            api_host="",
            staging_project_id=PROD_SUPABASE_PROJECT_REF,
            require_exact_project=True,
        )


def test_seed_refuses_a_non_staging_project_ref() -> None:
    with pytest.raises(StagingIsolationError):
        guard_seed_targets(
            supabase_url="https://someotherprojectref01.supabase.co",
            db_url="",
            api_host="",
            staging_project_id="someotherprojectref01",
            require_exact_project=True,
        )


def test_seed_allows_the_exact_staging_project_ref() -> None:
    guard_seed_targets(
        supabase_url=f"https://{STAGING_SUPABASE_PROJECT_REF}.supabase.co",
        db_url="",
        api_host="api.staging.vergeo5.com",
        staging_project_id=STAGING_SUPABASE_PROJECT_REF,
        require_exact_project=True,
    )


# ── Scanner credentials ───────────────────────────────────────────────────


def test_ticket_pin_seeding_fails_closed_without_the_service_role_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        mint_ticket_credentials()


def test_minted_pin_verifies_through_the_real_contract(service_role_key: str) -> None:
    credentials = mint_ticket_credentials()
    credential = credentials[0]
    assert verify_pin(
        pin=credential.pin,
        ticket_id=credential.ticket_id,
        pin_hash=credential.pin_hash,
    )


def test_a_tampered_pin_is_rejected(service_role_key: str) -> None:
    credential = mint_ticket_credentials()[0]
    wrong = "000000" if credential.pin != "000000" else "111111"
    assert not verify_pin(
        pin=wrong, ticket_id=credential.ticket_id, pin_hash=credential.pin_hash
    )


def test_pin_is_run_scoped_not_a_committed_constant(service_role_key: str) -> None:
    first = mint_ticket_credentials()[0]
    second = mint_ticket_credentials()[0]
    assert first.ticket_id == second.ticket_id, "ticket identity is canonical"
    assert (first.pin, first.qr_secret) != (second.pin, second.qr_secret)


def test_credential_repr_never_prints_the_pin(service_role_key: str) -> None:
    credential = mint_ticket_credentials()[0]
    assert credential.pin not in repr(credential)
    assert "<redacted>" in repr(credential)


def test_service_role_value_never_appears_in_seed_output_or_errors(
    service_role_key: str,
) -> None:
    credentials = mint_ticket_credentials()
    seed = build_seed_sql(credentials)
    assert SERVICE_ROLE_STUB not in seed
    # Only the sealed hash reaches SQL — never the PIN itself.
    assert credentials[0].pin_hash in seed
    assert credentials[0].pin not in seed


def test_primary_ticket_pin_requires_minted_credentials() -> None:
    with pytest.raises(RuntimeError):
        primary_ticket_pin(())


# ── Fixture version ───────────────────────────────────────────────────────


def test_fixture_version_is_stable_across_processes() -> None:
    script = (
        "import sys;sys.path.insert(0,'services/api');"
        "from app.staging.synthetic_contract import fixture_version;"
        "print(fixture_version())"
    )
    runs = {
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(2)
    }
    assert runs == {fixture_version()}


def test_fixture_version_excludes_run_scoped_credentials(service_role_key: str) -> None:
    before = fixture_version()
    credentials = mint_ticket_credentials()
    after = fixture_version()
    assert before == after, "minting a run PIN must not move fixture identity"
    document = json.dumps(canonical_contract_document(), default=str)
    assert credentials[0].pin not in document
    assert credentials[0].qr_secret not in document
    assert SERVICE_ROLE_STUB not in document


def test_fixture_version_changes_on_a_meaningful_contract_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = fixture_version()
    changed = replace(EVENTS[0], capacity=EVENTS[0].capacity + 1)
    monkeypatch.setattr("app.staging.synthetic_contract.EVENTS", (changed,))
    assert fixture_version() != baseline


# ── Generated TypeScript ──────────────────────────────────────────────────


def test_generated_fixtures_are_in_sync_with_the_python_contract() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/generate-e2e-fixtures.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_drift_guard_fails_when_the_generated_file_is_stale(tmp_path: Path) -> None:
    generated = REPO_ROOT / "e2e" / "fixtures" / "seed.generated.ts"
    original = generated.read_text(encoding="utf-8")
    try:
        generated.write_text(
            original.replace(SEED_PREFIX, "stg-rv-tampered"), encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, "scripts/ci/generate-e2e-fixtures.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "out of sync" in result.stderr
    finally:
        generated.write_text(original, encoding="utf-8")


def test_generated_typescript_carries_no_credentials(service_role_key: str) -> None:
    generated = (REPO_ROOT / "e2e" / "fixtures" / "seed.generated.ts").read_text(
        encoding="utf-8"
    )
    assert SERVICE_ROLE_STUB not in generated
    # Scan CODE only. The comments legitimately explain why OTP codes and the
    # scanner PIN are absent; matching that prose would be a false alarm. Strip
    # both // lines and /* */ blocks before looking for credential values.
    code = re.sub(r"/\*.*?\*/", "", generated, flags=re.DOTALL)
    code = "\n".join(
        line for line in code.splitlines() if not line.lstrip().startswith("//")
    )
    for forbidden in ("otp", "ticketpin", "pin_hash", "service_role", "secret"):
        assert forbidden not in code.lower(), (
            f"generated fixtures must not carry a {forbidden} value"
        )
    # It must carry the fixture version and the role-specific phones.
    assert fixture_version() in generated
    assert persona_by_key("CUSTOMER_A").phone in generated
    assert persona_by_key("APPROVED_VENDOR_A").phone in generated


def test_generated_typescript_publishes_both_lanes_but_no_scanner_ticket_id() -> None:
    """Fixture identity only. The scanner ticket id is run state, like the PIN.

    The paid lane stays published for the Lenco purchase journey, and the static
    hold is published under a name that says what it is, so nobody fills it into
    a scanner expecting a pass.
    """
    generated = (REPO_ROOT / "e2e" / "fixtures" / "seed.generated.ts").read_text(
        encoding="utf-8"
    )
    event = event_fixture("EVENT_LAUNCH_EXPO")
    assert f'paidTicketTypeName: "{paid_ticket_type(event).name}"' in generated
    assert f'scannerTicketTypeName: "{scanner_ticket_type(event).name}"' in generated
    assert f'unpaidHoldTicketId: "{event.tickets[0].ticket_id}"' in generated
    # The old key promised a scannable canonical ticket that never existed.
    assert "ticketId:" not in generated


# ── Private runtime material ──────────────────────────────────────────────


def _load_seed_script() -> Any:
    """Import the seeder CLI as a module (it lives outside the API package)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import seed_staging  # type: ignore[import-not-found]  # noqa: PLC0415

    return seed_staging


def _scanner_ticket_stub(pin: str = "424242") -> ScannerTicket:
    return ScannerTicket(
        ticket_id="9f1f4f1e-0000-4000-8000-00000000abcd",
        order_item_id="9f1f4f1e-0000-4000-8000-00000000abce",
        order_id="9f1f4f1e-0000-4000-8000-00000000abcf",
        checkout_group_id="9f1f4f1e-0000-4000-8000-00000000abd0",
        pin=pin,
        replayed=False,
    )


def test_private_runtime_file_is_mode_0600_and_holds_no_service_role_key(
    tmp_path: Path, service_role_key: str
) -> None:
    seed_staging = _load_seed_script()
    scanner = _scanner_ticket_stub()
    target = tmp_path / "convergeo-e2e-private.json"
    seed_staging._write_private_runtime_file(target, scanner)

    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    payload = json.loads(target.read_text(encoding="utf-8"))
    # The scanner TICKET ID ships with the PIN: rsvp() mints it per run, so it
    # cannot come from the generated contract.
    assert set(payload) == {"ticketPin", "ticketId"}
    assert payload["ticketPin"] == scanner.pin
    assert payload["ticketId"] == scanner.ticket_id
    assert SERVICE_ROLE_STUB not in target.read_text(encoding="utf-8")


def test_scanner_ticket_repr_never_prints_the_pin() -> None:
    scanner = _scanner_ticket_stub(pin="135791")
    assert scanner.pin not in repr(scanner)
    assert "<redacted>" in repr(scanner)


def test_seed_cli_reports_fixture_version_without_touching_a_database() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/seed_staging.py", "--env", "staging",
         "--print-fixture-version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == fixture_version()


# ── Workflow contract ─────────────────────────────────────────────────────


def _e2e_workflow() -> str:
    return (REPO_ROOT / ".github" / "workflows" / "e2e.yml").read_text(encoding="utf-8")


def test_exactly_one_destructive_seed_invocation_per_run() -> None:
    workflow = _e2e_workflow()
    mutating = re.findall(r"seed_staging\.py[^\n]*(?:\n[^\n]*)*?--apply", workflow)
    assert len(mutating) == 1, (
        f"expected exactly one mutating seed invocation, found {len(mutating)}"
    )
    assert "--cleanup" in workflow


def test_service_role_key_is_scoped_to_the_seed_step_only() -> None:
    workflow = _e2e_workflow()
    assert "STAGING_SUPABASE_SERVICE_ROLE_KEY" in workflow
    # Exactly one mapping, and it is the step-level one.
    assert workflow.count("secrets.STAGING_SUPABASE_SERVICE_ROLE_KEY") == 1
    job_env = workflow.split("    env:", 1)[1].split("    steps:", 1)[0]
    assert "SERVICE_ROLE" not in job_env, "service-role key must not be job-level env"


def test_workflow_seeds_only_after_the_target_guard_and_before_any_browser() -> None:
    workflow = _e2e_workflow()
    guard = workflow.index("Guard canonical seed target")
    seed = workflow.index("Canonical cleanup + seed (once per run)")
    browser = workflow.index("Install Playwright Chromium")
    assert guard < seed < browser


def test_workflow_publishes_the_run_scoped_scanner_ticket_id() -> None:
    """The spec cannot resolve the scanner ticket from source any more."""
    workflow = _e2e_workflow()
    assert "E2E_TICKET_ID=" in workflow
    publish = workflow.split("Publish fixture version", 1)[1].split("- name:", 1)[0]
    assert '"ticketId"' in publish
    # Published, but only after it is proven to be a UUID the seeder wrote.
    assert "malformed scanner ticket id" in publish


def test_workflow_masks_the_pin_and_cleans_up_always() -> None:
    workflow = _e2e_workflow()
    assert "::add-mask::" in workflow
    assert "E2E_TICKET_PIN=" in workflow
    assert "rm -f \"${RUNNER_TEMP}/convergeo-e2e-private.json\"" in workflow
    cleanup_block = workflow.split("Remove private runtime material", 1)[1]
    assert "always()" in cleanup_block.split("run:", 1)[0]


def test_workflow_no_longer_carries_the_reset_endpoint_contract() -> None:
    workflow = _e2e_workflow()
    for retired in ("E2E_SEED_RESET_URL", "E2E_SEED_TOKEN"):
        assert f"secrets.{retired}" not in workflow
    assert "internal/e2e/reset" not in workflow
