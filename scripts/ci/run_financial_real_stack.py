"""Run reviewed F1/F2 cases in runner-owned PostgreSQL without provider credentials.

New implementation from verified source. Not a recovery of the malformed inline
packet. Reuses the accepted replay, HTTP gateway, F2 upgrade probe and reporters.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from urllib.request import ProxyHandler, build_opener
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BASE = "8f78448e4b340787fae98eeee58c372cc5ded307"
PG_IMAGE = "pgvector/pgvector:0.8.0-pg17-trixie"
REST_IMAGE = "public.ecr.aws/supabase/postgrest:v14.14"
FORWARD = [
    "20260929120000_service_payment_obligations_and_claims.sql",
    "20260929120001_service_collection_settlement.sql",
    "20260929120002_funded_service_completion.sql",
    "20260929120003_adopt_existing_service_obligations.sql",
    "20260930170000_reconciliation_report_versions.sql",
    "20260930170100_vendor_stock_adjustment_authority.sql",
    "20260930203000_service_completion_variable_disambiguation.sql",
    "20260930203100_service_adoption_ambiguity_holds.sql",
    "20261001120000_merchant_protected_listing_admission.sql",
    "20261001120100_stock_claim_replay_authority.sql",
    "20261001120200_stock_claim_parent_lock_compatibility.sql",
]
F1_MODULE = "tests/test_f1_payout_real_stack.py"
F1_NODES = [
    F1_MODULE + "::test_real_postgrest_claim_rls_and_ledger_replay",
    F1_MODULE + "::test_real_postgres_reservation_lock_prevents_double_dispatch_capacity",
    *[F1_MODULE + "::test_real_postgrest_historical_pending_never_posts_again[" + x + "]"
      for x in ("successful", "pending", "failed", "not_found")],
]
F2_MODULES = [
    "tests/lane_d/test_f2_service_funding_postgrest.py",
    "tests/lane_d/test_f2_cancellation_postgrest.py",
]
RELATED = [
    "tests/test_order_state.py", "tests/test_job_completion.py",
    "tests/test_service_escrow.py", "tests/test_service_booking.py",
]


def validate_host() -> None:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "KaluMuso/Convergeo"
            or os.environ.get("GITHUB_SERVER_URL") != "https://github.com"
            or not os.environ.get("RUNNER_TEMP")):
        raise RuntimeError("Only the repository's disposable GitHub service job is permitted")
    for name in ("docker", "psql", "uv", "git"):
        if shutil.which(name) is None:
            raise RuntimeError(f"Required isolated-runner executable absent: {name}")


def nodes_from_collection(text: str) -> list[str]:
    return [s.strip() for s in text.splitlines() if s.startswith("tests/") and "::" in s]


def require_collection(expected: list[str], observed: list[str], status: int) -> None:
    if (status or not expected or len(expected) != len(set(expected))
            or len(observed) != len(set(observed)) or set(observed) != set(expected)):
        raise RuntimeError("Complete collection differs from reviewed required identities")


def financial_identities() -> dict[str, list[str]]:
    """Bind this NEW proposal's concrete inventory, without an approval claim."""
    manifest = json.loads((ROOT / "scripts/ci/coordinator-gate-inputs.json").read_text())
    identities: dict[str, list[str]] = manifest["financial"]
    for group, count in (("f1", 6), ("f2", 43), ("related", 755)):
        if len(identities[group]) != count or len(set(identities[group])) != count:
            raise RuntimeError("Financial concrete identity binding differs: " + group)
    require_collection(F1_NODES, identities["f1"], 0)
    require_collection((ROOT / "docs/ops/lenco/f2-required-nodes.txt")
                       .read_text().splitlines(), identities["f2"], 0)
    return identities


def load_reporter() -> ModuleType:
    """Load the checked-in CLI helper by file, not an ambient module search path."""
    path = ROOT / "scripts/drills/f2_real_stack_report.py"
    spec = importlib.util.spec_from_file_location("convergeo_financial_reporter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the repository financial evidence reporter")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    return report


class Runner:
    def __init__(self, output_name: str = "financial-real-stack-evidence") -> None:
        if output_name not in {"financial-real-stack-evidence", "coordinator-gate-evidence"}:
            raise RuntimeError("Unknown runner-owned evidence directory")
        self.output = ROOT / output_name
        if self.output.exists():
            raise RuntimeError("Refusing to reuse an existing financial evidence directory")
        self.output.mkdir()
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith(("LENCO_", "SUPABASE_", "PG", "LANE_D_", "ORDER_TEST_")):
                self.env.pop(key)
        self.env.update(
            PGHOST="127.0.0.1", PGPORT="54322", PGUSER="postgres", PGPASSWORD="postgres",
            ENV="development", SUPABASE_URL="http://127.0.0.1:3007",
            LENCO_ENV="sandbox", LENCO_SANDBOX_BASE_URL="http://127.0.0.1:9/access/v2",
            PAYMENTS_ENABLED="true", PAYMENTS_ALLOW_PRODUCTION="false",
            SUPABASE_REST_URL="http://127.0.0.1:3007/rest/v1",
            LANE_D_POSTGREST_URL="http://127.0.0.1:3006",
            LANE_D_JWT_SECRET=secrets.token_urlsafe(48),
            LANE_D_WEBHOOK_TOKEN=secrets.token_urlsafe(48),
            NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
            PYTHONPATH=str(ROOT / "services/api") + os.pathsep + str(ROOT / "scripts/drills"),
        )
        from critical_real_stack_http import role_token
        self.env["SUPABASE_SERVICE_ROLE_KEY"] = role_token(
            "service_role", self.env["LANE_D_JWT_SECRET"]
        )
        self.env["SUPABASE_ANON_KEY"] = role_token("anon", self.env["LANE_D_JWT_SECRET"])
        self.env["LENCO_API_TOKEN"] = self.env["LANE_D_WEBHOOK_TOKEN"]
        self.password = secrets.token_urlsafe(24)
        self.dbs: list[str] = []
        self.steps: dict[str, int] = {}
        self.results: dict[str, object] = {"accepted": False, "phases": {}, "steps": self.steps}
        self.raw = Path(tempfile.mkdtemp(prefix="financial-raw-", dir=self.env["RUNNER_TEMP"]))

    def redact(self, text: str) -> str:
        for key in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "LANE_D_JWT_SECRET",
                    "LANE_D_WEBHOOK_TOKEN", "SUPABASE_DB_URL", "ORDER_TEST_DB_URL"):
            value = self.env.get(key)
            if value:
                text = text.replace(value, "[REDACTED]")
        return text.replace(self.password, "[REDACTED]").replace(
            "postgres:postgres@", "postgres:[REDACTED]@")

    def command(self, name: str, args: list[str], *, cwd: Path = ROOT,
                checked: bool = True, timeout: int = 1800) -> tuple[int, str]:
        p = subprocess.Popen(args, cwd=cwd, env=self.env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            text, _ = p.communicate(timeout=timeout)
            status = p.returncode
        except subprocess.TimeoutExpired:
            # Only the subprocess group created immediately above, never another agent/runner.
            os.killpg(p.pid, signal.SIGKILL)
            text, _ = p.communicate()
            text += "\nOWNED_COMMAND_TIMEOUT\n"
            status = 124
        self.steps[name] = status
        (self.output / (name + ".log")).write_text(self.redact(text))
        with (self.output / "commands.jsonl").open("a") as f:
            f.write(json.dumps({"step": name, "command": [self.redact(a) for a in args],
                                "exit": status, "cwd": str(cwd)}) + "\n")
        if checked and status:
            raise RuntimeError(f"{name} failed with exit {status}; see sanitized log")
        return status, text

    def sql(self, name: str, database: str, statement: str) -> str:
        return self.command(name, ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-Atq",
                                   "-d", database, "-c", statement])[1].strip()

    def create(self, database: str, template: str = "template0") -> None:
        if not re.fullmatch(r"ci_(?:critical|financial)_[a-z_]+", database):
            raise RuntimeError("Database name outside this job's disposable namespace")
        self.sql("create-" + database, "postgres",
                 f'CREATE DATABASE "{database}" TEMPLATE "{template}"')
        self.dbs.append(database)

    def drop(self, database: str) -> None:
        if database not in self.dbs:
            raise RuntimeError("Refusing to drop a database not created by this run")
        self.sql("drop-" + database, "postgres", f'DROP DATABASE "{database}" WITH (FORCE)')
        self.dbs.remove(database)

    def bootstrap(self, database: str, group: str) -> None:
        self.sql("auth-columns-" + database, database, """
          ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS instance_id uuid,
            ADD COLUMN IF NOT EXISTS aud text, ADD COLUMN IF NOT EXISTS role text,
            ADD COLUMN IF NOT EXISTS encrypted_password text,
            ADD COLUMN IF NOT EXISTS email_confirmed_at timestamptz,
            ADD COLUMN IF NOT EXISTS raw_app_meta_data jsonb,
            ADD COLUMN IF NOT EXISTS raw_user_meta_data jsonb,
            ADD COLUMN IF NOT EXISTS updated_at timestamptz;
          CREATE TABLE IF NOT EXISTS public.ci_critical_binding_probe
            (group_name text NOT NULL, database_name text NOT NULL);
          REVOKE ALL ON public.ci_critical_binding_probe FROM PUBLIC, anon, authenticated;
          GRANT SELECT ON public.ci_critical_binding_probe TO service_role;
          TRUNCATE public.ci_critical_binding_probe;
        """ + f"INSERT INTO public.ci_critical_binding_probe "
              f"VALUES ('{group}',current_database());")
        self.command("auth-shim-" + database,
                     ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", database,
                     "-f", str(ROOT / "services/api/tests/lane_d/local_postgrest_auth_shim.sql")])

    def bind(self, database: str) -> None:
        dsn = f"postgresql://postgres:postgres@127.0.0.1:54322/{database}"
        self.env.update(SUPABASE_DB_URL=dsn, ORDER_TEST_DB_URL=dsn, FIXB_TEST_DB_URL=dsn)

    @contextlib.contextmanager
    def rest(self, group: str, database: str, label: str) -> Iterator[None]:
        self.bind(database)
        self.bootstrap(database, group)
        _, cid = self.command(label + "-rest-start",
                              ["docker", "run", "-d", "--rm", "--network", "host",
            "--label", "convergeo.disposable=financial-ci",
            "-e", f"PGRST_DB_URI=postgresql://ci_critical_authenticator:"
                  f"{self.password}@127.0.0.1:54322/{database}",
            "-e", "PGRST_DB_SCHEMAS=public", "-e", "PGRST_DB_ANON_ROLE=anon",
            "-e", "PGRST_JWT_SECRET=" + self.env["LANE_D_JWT_SECRET"],
            "-e", "PGRST_SERVER_HOST=127.0.0.1", "-e", "PGRST_SERVER_PORT=3006", REST_IMAGE])
        cid = cid.strip()
        if not re.fullmatch(r"[a-f0-9]{64}", cid):
            raise RuntimeError("Invalid newly created PostgREST container identity")
        # Register container cleanup before token refresh, log creation or Popen.
        # ExitStack executes ALL callbacks even when an earlier cleanup raises.
        with contextlib.ExitStack() as cleanup:
            cleanup.callback(self.command, label + "-rest-stop", ["docker", "rm", "-f", cid])
            self.env["F2_POSTGREST_CONTAINER"] = cid
            cleanup.callback(self.env.pop, "F2_POSTGREST_CONTAINER", None)
            from critical_real_stack_http import role_token
            self.env["SUPABASE_SERVICE_ROLE_KEY"] = role_token(
                "service_role", self.env["LANE_D_JWT_SECRET"]
            )
            self.env["SUPABASE_ANON_KEY"] = role_token("anon", self.env["LANE_D_JWT_SECRET"])
            handle = (self.raw / (label + "-gateway.log")).open("w")
            # LIFO order: gateway shutdown, handle close, sanitized log, Docker rm.
            cleanup.callback(self.retain_gateway_log, label)
            cleanup.callback(handle.close)
            gateway = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts/ci/critical_real_stack_http.py"), "gateway"],
                env=self.env, stdout=handle, stderr=subprocess.STDOUT,
            )
            cleanup.callback(self.stop_gateway, gateway)
            opener = build_opener(ProxyHandler({}))
            for _attempt in range(30):
                if gateway.poll() is not None:
                    raise RuntimeError("Owned gateway exited before readiness")
                try:
                    with opener.open("http://127.0.0.1:3007/rest/v1/", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Local REST service did not become ready")
            self.command(label + "-preflight", ["uv", "run", "--no-sync", "python",
                "../../scripts/ci/critical_real_stack_http.py", "preflight", "--group", group,
                "--database", database, "--container", cid], cwd=ROOT / "services/api")
            yield

    @staticmethod
    def stop_gateway(gateway: subprocess.Popen[bytes]) -> None:
        gateway.terminate()
        try:
            gateway.wait(timeout=10)
        except subprocess.TimeoutExpired:
            gateway.kill()
            gateway.wait(timeout=10)

    def retain_gateway_log(self, label: str) -> None:
        (self.output / (label + "-gateway.log")).write_text(
            self.redact((self.raw / (label + "-gateway.log")).read_text()))

    def pytest(self, label: str, selectors: list[str], *, collect: bool = False,
               plugin: str | None = None) -> tuple[int, str]:
        args = ["uv", "run", "--no-sync", "pytest", "-q", "-rA", "-o", "xfail_strict=true"]
        if plugin:
            args += ["-p", plugin]
        args += ["--collect-only", "--disable-warnings"] if collect else [
            "--junitxml=" + str(self.raw / (label + ".xml"))]
        status, text = self.command(
            label, args + selectors, cwd=ROOT / "services/api", checked=False
        )
        if not collect and (self.raw / (label + ".xml")).is_file():
            (self.output / (label + ".xml")).write_text(
                self.redact((self.raw / (label + ".xml")).read_text()))
        return status, text

    def phase(self, phase: str, template: str, f2db: str) -> None:
        report = load_reporter()
        identities = financial_identities()
        results: dict[str, object] = {}
        phases = self.results["phases"]
        assert isinstance(phases, dict)
        phases[phase] = results
        # F1 state is isolated from both F2 and the related fixture modules.
        self.create("ci_critical_cart", template)
        self.env.update(F1_REAL_STACK_DATABASE="ci_critical_cart", F1_REAL_STACK_GROUP="cart")
        with self.rest("cart", "ci_critical_cart", phase + "-f1"):
            label = phase + "-f1"
            rc, text = self.pytest(label + "-collection", [F1_MODULE], collect=True)
            require_collection(F1_NODES, nodes_from_collection(text), rc)
            (self.output / (label + "-expected.txt")).write_text("\n".join(F1_NODES) + "\n")
            rc, _ = self.pytest(label, [F1_MODULE])
            results["f1"], _ = report._reconcile(F1_NODES, self.output / (label + ".xml"), rc)
        self.drop("ci_critical_cart")
        self.env.pop("F1_REAL_STACK_DATABASE")
        self.env.pop("F1_REAL_STACK_GROUP")
        group = "collection" if phase == "pristine" else "prepaid"
        with self.rest(group, f2db, phase + "-f2"):
            label = phase + "-f2"
            expected = (ROOT / "docs/ops/lenco/f2-required-nodes.txt").read_text().splitlines()
            if len(expected) != 43:
                raise RuntimeError("Reviewed 43-identity F2 manifest changed; rebind the gate")
            rc, text = self.pytest(label + "-collection", F2_MODULES, collect=True)
            require_collection(expected, nodes_from_collection(text), rc)
            rc, _ = self.pytest(label, F2_MODULES)
            results["f2"], _ = report._reconcile(expected, self.output / (label + ".xml"), rc)
        # Collect the complete related universe before any individual module runs.
        self.env["F2_COLLECTION_OUTPUT"] = str(self.output / (phase + "-related-collected.json"))
        rc, _ = self.pytest(phase + "-related-collection", RELATED, collect=True,
                            plugin="f2_collection_manifest")
        collection_rc = rc
        collected = json.loads(Path(self.env["F2_COLLECTION_OUTPUT"]).read_text())
        require_collection(identities["related"], collected["nodeids"], collection_rc)
        xml_root = ET.Element("testsuites")
        exits: list[int] = []
        related_groups = ("checkout", "kyc", "tickets", "creation")
        for i, (module, related_group) in enumerate(zip(RELATED, related_groups, strict=True)):
            database = "ci_critical_" + related_group
            self.create(database, template)
            label = f"{phase}-related-{i}"
            with self.rest(related_group, database, label):
                rc, _ = self.pytest(label, [module])
                exits.append(rc)
            report_path = self.output / (label + ".xml")
            if report_path.is_file():
                xml_root.append(ET.parse(report_path).getroot())
            else:
                exits.append(1)
            self.drop(database)
        merged = self.output / (phase + "-related.xml")
        ET.ElementTree(xml_root).write(merged, encoding="unicode")
        related, _ = report.related_report(Path(self.env.pop("F2_COLLECTION_OUTPUT")), merged,
                                          int(any(exits)), collection_rc)
        # Reviewer bound 755 identities. Do not silently accept a reduced collection.
        if related.get("expected") != 755:
            related["accepted"] = False
            related["inventory_error"] = (
                "Expected the independently reviewed 755 related identities"
            )
        results["related"] = related
        self.write_result()

    def write_result(self) -> None:
        path = self.output / "results.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.results, indent=2) + "\n")
        temp.replace(path)

    def execute(self) -> None:
        _, ids = self.command("postgres-containers",
                              ["docker", "ps", "--filter", "ancestor=" + PG_IMAGE,
                               "--format", "{{.ID}}"])
        containers = ids.splitlines()
        if len(containers) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", containers[0]):
            raise RuntimeError("Expected one repository job-owned pgvector service")
        _, ports = self.command("postgres-port", ["docker", "port", containers[0], "5432/tcp"])
        if not ports.strip() or any(not line.endswith(":54322") for line in ports.splitlines()):
            raise RuntimeError("Postgres is not bound to the reserved loopback client port")
        self.command("postgres-image",
                     ["docker", "inspect", "--format", "{{.Image}}", containers[0]])
        if self.sql("postgres-version", "postgres", "SHOW server_version_num") != "170006":
            raise RuntimeError("The disposable database is not PostgreSQL 17.6")
        self.command("source", ["git", "rev-parse", "HEAD", "HEAD^{tree}"])
        expected_sha = self.env.get("QUALIFICATION_SHA")
        if expected_sha:
            _, actual_sha = self.command("exact-review-sha", ["git", "rev-parse", "HEAD"])
            if actual_sha.strip() != expected_sha:
                raise RuntimeError("Financial checkout differs from the exact review SHA")
        self.command("clean-worktree", ["git", "diff", "--exit-code"])
        self.command("clean-index", ["git", "diff", "--cached", "--exit-code"])
        self.command("baseline-present", ["git", "cat-file", "-e", BASE + "^{commit}"])
        base_dir = Path(tempfile.mkdtemp(prefix="financial-baseline-", dir=self.env["RUNNER_TEMP"]))
        archive = self.raw / "baseline.tar"
        self.command("baseline-ancestry", ["git", "merge-base", "--is-ancestor", BASE, "HEAD"])
        self.command("baseline-export",
                     ["git", "archive", "--format=tar", "--output=" + str(archive),
                      BASE, "supabase/migrations", "scripts/ci/migration-replay.sh"])
        with tarfile.open(archive) as tf:
            # Own Git archive, nevertheless reject links and path escapes.
            for member in tf:
                target = base_dir / member.name
                if (not target.resolve().is_relative_to(base_dir.resolve())
                        or member.issym() or member.islnk()):
                    raise RuntimeError("Unexpected baseline archive member")
                tf.extract(member, base_dir, filter="data")
        baseline = base_dir / "supabase/migrations"
        current = ROOT / "supabase/migrations"
        old = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in baseline.glob("*.sql")}
        new = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in current.glob("*.sql")}
        if len(old) != 127 or len(new) != 138 or set(new) - set(old) != set(FORWARD):
            raise RuntimeError("Unexpected source-bound migration inventory")
        if any(new.get(k) != v for k, v in old.items()):
            raise RuntimeError("An accepted baseline migration was modified or removed")
        (self.output / "migration-inputs.json").write_text(
            json.dumps({"base": old, "candidate": new}, indent=2)
        )
        self.create("ci_financial_pristine")
        self.env["PGDATABASE"] = "ci_financial_pristine"
        self.command("pristine-migration-replay", ["bash", "scripts/ci/migration-replay.sh"])
        if self.sql("vector-version", "ci_financial_pristine",
                    "SELECT extversion FROM pg_extension WHERE extname='vector'") != "0.8.0":
            raise RuntimeError("Unexpected vector version for this qualification profile")
        self.sql("authenticator-create", "postgres", "CREATE ROLE ci_critical_authenticator LOGIN "
                 f"NOINHERIT NOSUPERUSER NOBYPASSRLS PASSWORD '{self.password}'; "
                 "GRANT anon,authenticated,service_role TO ci_critical_authenticator;")
        roles = self.sql("roles", "postgres", "SELECT rolname||'|'||rolsuper::text||'|'||"
                         "rolbypassrls::text||'|'||rolinherit::text FROM pg_roles WHERE rolname IN "
                         "('ci_critical_authenticator','anon','authenticated','service_role') "
                         "ORDER BY rolname")
        if "ci_critical_authenticator|false|false|false" not in roles:
            raise RuntimeError("PostgREST login unexpectedly inherits authority")
        for name in ("anon", "authenticated"):
            if not any(row.startswith(name + "|false|false|") for row in roles.splitlines()):
                raise RuntimeError("Browser role has unexpected superuser/BYPASSRLS")
        self.command("postgrest-pull", ["docker", "pull", REST_IMAGE])
        _, version = self.command("postgrest-version", ["docker", "run", "--rm", "--entrypoint",
                                                       "postgrest", REST_IMAGE, "--version"])
        if re.search(r"\b14\.14(?:\b|\.)", version) is None:
            raise RuntimeError("Unexpected PostgREST binary version")
        self.command("postgrest-image", ["docker", "image", "inspect", REST_IMAGE])
        self.create("ci_critical_collection", "ci_financial_pristine")
        self.phase("pristine", "ci_financial_pristine", "ci_critical_collection")
        self.drop("ci_critical_collection")
        self.create("ci_critical_prepaid")
        self.env["PGDATABASE"] = "ci_critical_prepaid"
        self.command("upgrade-baseline-replay",
                     ["bash", str(base_dir / "scripts/ci/migration-replay.sh")])
        self.bootstrap("ci_critical_prepaid", "prepaid")
        self.bind("ci_critical_prepaid")
        upgrade = self.raw / "upgrade-fingerprint.json"
        args = ["uv", "run", "--no-sync", "python", "../../scripts/drills/f2_upgrade_probe.py"]
        self.command("upgrade-seed", args + ["seed", str(upgrade)], cwd=ROOT / "services/api")
        for filename in FORWARD:
            if filename == "20260929120003_adopt_existing_service_obligations.sql":
                self.command("upgrade-" + filename.split("_")[0],
                             [sys.executable, str(ROOT / "scripts/ci/apply_service_adoption.py")])
            else:
                self.command("upgrade-" + filename.split("_")[0],
                             ["psql", "-X", "-v", "ON_ERROR_STOP=1",
                              "-d", "ci_critical_prepaid", "-f", str(current / filename)])
        self.command("upgrade-verify", args + ["verify", str(upgrade)], cwd=ROOT / "services/api")
        (self.output / "upgrade-fingerprint.json").write_text(self.redact(upgrade.read_text()))
        self.create("ci_financial_upgrade", "ci_critical_prepaid")
        self.phase("upgrade", "ci_financial_upgrade", "ci_critical_prepaid")
        phases = self.results["phases"]
        assert isinstance(phases, dict)
        self.results["accepted"] = (
            set(phases) == {"pristine", "upgrade"}
            and all(isinstance(p, dict) and set(p) == {"f1", "f2", "related"}
                    and all(isinstance(r, dict) and r.get("accepted") is True for r in p.values())
                    for p in phases.values())
            and not any(self.steps.values())
        )

    def finish(self) -> None:
        for database in list(reversed(self.dbs)):
            try:
                self.drop(database)
            except Exception as exc:
                self.results["accepted"] = False
                self.results["cleanup_error"] = str(exc)
        self.write_result()


def main() -> int:
    validate_host()  # No database, network or runtime operation precedes this check.
    runner = Runner()
    try:
        runner.execute()
    except Exception as exc:
        runner.results["accepted"] = False
        runner.results["error"] = runner.redact(str(exc))
    finally:
        runner.finish()
    print("FINANCIAL_REAL_STACK_PASS" if runner.results["accepted"]
          else "FINANCIAL_REAL_STACK_INCOMPLETE")
    return 0 if runner.results["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
