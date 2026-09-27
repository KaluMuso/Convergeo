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
    collect = security.index("Collect trusted authorization matrix inventory")
    execute = security.index("Route x role authz matrix (sole owner, no DB)")
    prove = security.index("Prove the authz matrix ran (no silent skip)")
    assert collect < execute < prove
    assert "assert_authz_matrix_ran.py collect" in security
    assert "--inventory authz-matrix-expected.json" in security
    assert '--checkout-sha "${GITHUB_SHA}"' in security
    assert "--junitxml=authz-matrix.xml" in security
    assert "if: always()" in security
    assert "assert_authz_matrix_ran.py validate authz-matrix.xml" in security
    assert "services/api/authz-matrix-expected.json" in security

    guard = (REPO_ROOT / "scripts" / "ci" / "assert_authz_matrix_ran.py").read_text(
        encoding="utf-8"
    )
    assert "MINIMUM_CASES" not in guard
    assert "expected testcase identities missing" in guard
    assert "unexpected testcase identities" in guard


def _active_lines(source: str) -> str:
    """Exclude YAML and SQL comments from the executable contract."""
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("#", "--"))
    )


def _rls_steps(rls: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^      - name: ", rls.split("    steps:\n", 1)[1])
    return [(part.split("\n", 1)[0], part) for part in parts[1:]]


def _rls_isolation_contract(ci: str, provision: str, verifier: str, fixture: str) -> None:
    match = re.search(r"(?ms)^  rls:\n.*?(?=^  [a-z0-9-]+:\n|\Z)", ci)
    assert match is not None, "RLS job missing"
    rls = _active_lines(match.group(0))
    header, _ = rls.split("    steps:\n", 1)
    steps = _rls_steps(rls)
    named = dict(steps)
    names = [name for name, _ in steps]
    assert "if:" not in header and "continue-on-error:" not in rls, "RLS job must block"

    service = re.search(r"(?ms)^    services:\n(.*?)(?=^    [a-z][\w-]*:|\Z)", header)
    assert service is not None and re.search(r"(?m)^      postgres:$", service.group(1)), (
        "disposable PostgreSQL service"
    )
    assert re.findall(r"(?m)^      [\w-]+:$", service.group(1)) == ["      postgres:"], (
        "unexpected service"
    )
    assert re.search(
        r"(?m)^        image: pgvector/pgvector:0\.8\.0-pg17-trixie$", service.group(1)
    ), (
        "qualified disposable PostgreSQL image missing"
    )
    ports = re.findall(r"(?m)^          - (\d+):5432$", service.group(1))
    assert ports == ["54322"], "PostgreSQL service must expose local port 54322"

    db_url = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    job_env = re.search(r"(?ms)^    env:\n(.*?)(?=^    [a-z][\w-]*:|\Z)", header)
    assert job_env is not None, "RLS job database environment missing"
    assert [
        value.strip() for value in re.findall(r"(?m)^      SUPABASE_DB_URL:(.*)$", job_env.group(1))
    ] == [db_url], (
        "RLS database target must be loopback on the disposable service"
    )
    for name, body in steps:
        overrides = [
            value.strip() for value in re.findall(r"(?m)^          SUPABASE_DB_URL:(.*)$", body)
        ]
        assert not overrides or overrides == [db_url], f"{name} overrides the local database target"
        assert not re.search(r"(?m)^        if:|^        continue-on-error:", body), (
            f"{name} must execute and block"
        )
        assert not re.search(r"\|\|\s*true\b|\bset\s+\+e\b", body), (
            f"{name} must not suppress failures"
        )

    replay = named.get("Replay migrations", "")
    for key, value in (
        ("PGHOST", "localhost"), ("PGPORT", "54322"),
        ("PGUSER", "postgres"), ("PGDATABASE", "postgres"),
    ):
        assert re.search(rf"(?m)^          {key}: {value}$", replay), (
            f"migration replay {key} mismatch"
        )
    assert re.search(r"(?m)^        run: bash scripts/ci/migration-replay\.sh$", replay), (
        "migration replay absent"
    )
    assert names.index("Replay migrations") < names.index(
        "DB-backed integration (curated, isolation-clean)"
    ), (
        "migration replay must precede tests"
    )
    assert names.index("Replay migrations") < names.index("RLS isolation matrix"), (
        "migration replay must precede matrix"
    )
    assert not re.search(
        r"(?im)\b(?:scripts/seed(?:_staging)?\.py|supabase db (?:reset|seed)|"
        r"--seed|seed\.sql)\b",
        rls,
    ), (
        "RLS job must not run a demo seed"
    )

    role = named.get("Provision RLS tester role", "")
    assert re.search(
        r'psql "\$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 '
        r'-f ../../scripts/ci/provision-rls-tester\.sql',
        role,
    ), (
        "checked RLS tester provisioning missing"
    )
    assert "exit 1" in role, "role provisioning failure must stop the job"
    assert re.search(
        r"CREATE ROLE vergeo_rls_tester\b[^;]*\bNOSUPERUSER\s+NOBYPASSRLS\b",
        _active_lines(provision),
    ), (
        "tester must be NOSUPERUSER and NOBYPASSRLS"
    )
    for browser_role in ("anon", "authenticated"):
        assert re.search(
            rf"GRANT {browser_role} TO vergeo_rls_tester;", _active_lines(provision)
        ), (
            f"tester needs {browser_role} membership"
        )
    assert "IF attrs IS DISTINCT FROM 'false,false'" in _active_lines(provision), (
        "tester privilege assertion missing"
    )
    assert "IF memberships < 2" in _active_lines(provision), "tester membership assertion missing"
    verify = named.get("Verify PostgreSQL/vector runtime and role shape", "")
    assert re.search(r"bash ../../scripts/ci/verify-postgres-runtime\.sh", verify), (
        "runtime verification missing"
    )
    assert (
        "vergeo_rls_tester" in _active_lines(verifier)
        and '${role}|f|f' in _active_lines(verifier)
    ), (
        "runtime verifier must reject privileged tester"
    )
    assert names.index("Provision RLS tester role") < names.index(
        "Verify PostgreSQL/vector runtime and role shape"
    ), (
        "role provisioning must precede verification"
    )
    assert names.index("Verify PostgreSQL/vector runtime and role shape") < names.index(
        "DB-backed integration (curated, isolation-clean)"
    ), (
        "runtime verification must precede database tests"
    )
    curated = named["DB-backed integration (curated, isolation-clean)"]
    matrix = named["RLS isolation matrix"]
    assert re.search(
        r"(?m)^        run: uv run pytest tests/test_db_adapter\.py .+ -q$", curated
    ), (
        "curated database suite must execute"
    )
    assert re.search(r"(?m)^        run: uv run pytest tests/rls -q$", matrix), (
        "RLS matrix must execute"
    )
    assert "seed_matrix_fixtures(conn)" in fixture, "matrix fixture must own its seed"


def test_rls_job_has_truthful_isolated_data_preconditions() -> None:
    _rls_isolation_contract(
        CI,
        (REPO_ROOT / "scripts/ci/provision-rls-tester.sql").read_text(encoding="utf-8"),
        (REPO_ROOT / "scripts/ci/verify-postgres-runtime.sh").read_text(encoding="utf-8"),
        (REPO_ROOT / "services/api/tests/rls/conftest.py").read_text(encoding="utf-8"),
    )


def test_rls_isolation_contract_rejects_unsafe_mutations() -> None:
    provision = (REPO_ROOT / "scripts/ci/provision-rls-tester.sql").read_text(encoding="utf-8")
    verifier = (REPO_ROOT / "scripts/ci/verify-postgres-runtime.sh").read_text(encoding="utf-8")
    fixture = (REPO_ROOT / "services/api/tests/rls/conftest.py").read_text(encoding="utf-8")

    def mutate_job(before: str, after: str) -> str:
        prefix, job_and_later = CI.split("  rls:\n", 1)
        rls, later = job_and_later.split("  money-db-triggers:\n", 1)
        assert before in rls, f"mutation target absent: {before}"
        return (
            prefix + "  rls:\n" + rls.replace(before, after, 1)
            + "  money-db-triggers:\n" + later
        )

    replay = "run: bash scripts/ci/migration-replay.sh"
    local_url = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    role_sql = "CREATE ROLE vergeo_rls_tester LOGIN PASSWORD 'test' NOSUPERUSER NOBYPASSRLS"
    cases = (
        (
            "service",
            mutate_job(
                "      postgres:\n        image: pgvector",
                "      shared_db:\n        image: pgvector",
            ),
            provision, verifier, "service",
        ),
        (
            "image",
            mutate_job("image: pgvector/pgvector:0.8.0-pg17-trixie", "image: postgres:latest"),
            provision, verifier, "image",
        ),
        (
            "port", mutate_job("          - 54322:5432", "          - 54323:5432"),
            provision, verifier, "port",
        ),
        (
            "replay port", mutate_job("          PGPORT: 54322", "          PGPORT: 5432"),
            provision, verifier, "PGPORT",
        ),
        (
            "shared", mutate_job(local_url, "${{ secrets.SHARED_DATABASE_URL }}"),
            provision, verifier, "loopback",
        ),
        (
            "override",
            mutate_job(
                "          PGHOST: localhost\n          PGPORT: 54322",
                "          PGHOST: localhost\n"
                "          SUPABASE_DB_URL: ${{ secrets.SHARED_DATABASE_URL }}\n"
                "          PGPORT: 54322",
            ),
            provision, verifier, "overrides",
        ),
        ("replay", mutate_job(replay, "run: echo replay"), provision, verifier, "replay absent"),
        (
            "suppressed replay", mutate_job(replay, replay + " || true"),
            provision, verifier, "suppress failures",
        ),
        (
            "seed",
            mutate_job(
                replay, replay + "\n\n      - name: Seed demo\n        run: python scripts/seed.py"
            ),
            provision, verifier, "demo seed",
        ),
        (
            "role",
            mutate_job(
                "-f ../../scripts/ci/provision-rls-tester.sql", "-f ../../scripts/ci/missing.sql"
            ),
            provision, verifier, "provisioning",
        ),
        (
            "verification",
            mutate_job("bash ../../scripts/ci/verify-postgres-runtime.sh", "echo verified"),
            provision, verifier, "verification",
        ),
        (
            "skipped verification",
            mutate_job(
                "      - name: Verify PostgreSQL/vector runtime and role shape\n",
                "      - name: Verify PostgreSQL/vector runtime and role shape\n"
                "        if: false\n",
            ),
            provision, verifier, "execute and block",
        ),
        (
            "missing curated",
            mutate_job(
                "run: uv run pytest tests/test_db_adapter.py",
                "run: echo skipped tests/test_db_adapter.py",
            ),
            provision, verifier, "curated database suite",
        ),
        (
            "missing matrix", mutate_job("run: uv run pytest tests/rls -q", "run: echo skipped"),
            provision, verifier, "RLS matrix must execute",
        ),
        (
            "privilege", CI, provision.replace(role_sql, role_sql.replace("NO", ""), 1),
            verifier, "NOSUPERUSER",
        ),
        (
            "membership", CI,
            provision.replace(
                "GRANT anon TO vergeo_rls_tester;", "-- GRANT anon TO vergeo_rls_tester;", 1
            ),
            verifier, "anon membership",
        ),
    )
    for label, mutated_ci, mutated_provision, mutated_verifier, reason in cases:
        try:
            _rls_isolation_contract(mutated_ci, mutated_provision, mutated_verifier, fixture)
        except AssertionError as exc:
            assert reason in str(exc), f"{label} rejected for an unrelated reason: {exc}"
        else:
            raise AssertionError(f"unsafe {label} mutation was accepted")


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
