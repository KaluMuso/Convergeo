from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CI = CI_PATH.read_text(encoding="utf-8")


def job_block(job_id: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job_id)}:\n.*?(?=^  [a-z0-9-]+:\n|\Z)", CI)
    assert match is not None, f"missing CI job: {job_id}"
    return match.group(0)


def test_required_check_context_names_remain_stable() -> None:
    expected = {
        "js": "JavaScript / TypeScript",
        "python": "Python API",
        "security-gates": "Security gates (headers + authz matrix)",
        "migrations": "Migration replay (fast)",
        "db": "Database / typegen drift",
        "rls": "RLS isolation matrix",
        "money-db-triggers": "Money DB-trigger integration",
        "cod-container-smoke": "COD production-container smoke",
        "secret-scan": "Secret scan (gitleaks)",
    }
    for job_id, context in expected.items():
        assert f"    name: {context}\n" in job_block(job_id)


def test_authorization_matrix_has_one_unconditional_owner() -> None:
    python = job_block("python")
    security = job_block("security-gates")
    security_header = security.split("    steps:", maxsplit=1)[0]

    assert "uv run pytest --ignore=tests/test_authz_matrix.py" in python
    assert CI.count("uv run pytest tests/test_authz_matrix.py") == 1
    assert "if:" not in security_header
    assert re.search(r"(?m)^\s+continue-on-error:", security) is None
    assert "--junitxml=authz-matrix.xml" in security
    assert "if: always()" in security
    assert "assert_authz_matrix_ran.py authz-matrix.xml" in security


def test_rls_job_has_truthful_isolated_data_preconditions() -> None:
    rls = job_block("rls")
    rls_fixture = (
        REPO_ROOT / "services" / "api" / "tests" / "rls" / "conftest.py"
    ).read_text(encoding="utf-8")

    assert "supabase db reset --no-seed" in rls
    assert "scripts/seed.py" not in rls
    assert re.search(r"(?m)^\s+continue-on-error:", rls) is None
    assert "seed_matrix_fixtures(conn)" in rls_fixture


def test_curated_database_and_rls_suites_remain_blocking() -> None:
    rls = job_block("rls")
    curated = (
        "tests/test_db_adapter.py",
        "tests/test_ticket_purchase.py",
        "tests/test_ticket_verify.py",
        "tests/test_ticket_wallet.py",
        "tests/test_ticket_scan_sync.py",
        "tests/test_ticket_transfer.py",
        "tests/test_event_release.py",
        "tests/test_search_analytics.py",
        "tests/test_service_escrow.py",
        "tests/test_vendor_analytics.py",
        "tests/test_review_aggregate.py",
        "tests/test_listing_below_median.py",
        "tests/test_kyc_state.py",
    )
    for test_path in curated:
        assert test_path in rls
    assert "uv run pytest tests/rls -q" in rls
    assert re.search(r"(?m)^\s+continue-on-error:", rls) is None


def test_five_outbox_cases_keep_their_no_silent_skip_guard() -> None:
    money = job_block("money-db-triggers")
    guard = (REPO_ROOT / "scripts" / "ci" / "assert_outbox_regression_ran.py").read_text(
        encoding="utf-8"
    )
    expected_cases = (
        "test_cleanup_deletes_outbox_rows_linked_only_by_checkout_group_id",
        "test_cleanup_deletes_outbox_rows_linked_only_by_order_id",
        "test_cleanup_preserves_outbox_rows_for_a_real_non_namespace_order",
        "test_cleanup_preserves_unrelated_outbox_rows",
        "test_repeat_cleanup_is_idempotent_and_leaves_no_outbox_residue",
    )

    assert "uv run pytest tests/test_seed_staging.py -q" in money
    assert "if: always()" in money
    assert "assert_outbox_regression_ran.py staging-cleanup-regression.xml" in money
    for case in expected_cases:
        assert case in guard
