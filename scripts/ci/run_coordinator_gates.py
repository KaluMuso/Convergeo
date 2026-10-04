"""NEW proposal: bind retained F3, merchant and curated/RLS to owned CI resources.

This does not recover the missing historical five-path artifact or approve it.
Reuse the existing financial command/JUnit/cleanup helpers, without provider calls.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import json
import re
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import run_financial_real_stack as financial
from critical_real_stack_http import role_token

ROOT = financial.ROOT
F3_MIGRATION = "20260930170000_reconciliation_report_versions.sql"
INPUTS = ROOT / "scripts/ci/coordinator-gate-inputs.json"


def inputs() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(INPUTS.read_text())
    if data.get("schema") != "convergeo.coordinator.new-proposal.v1":
        raise RuntimeError("Unknown coordinator input contract")
    for key, count in (("f3", 7), ("db", 26), ("review_db", 18), ("ui", 6), ("normal", 267)):
        if len(data[key]) != count or len(set(data[key])) != count:
            raise RuntimeError("Retained identity inventory changed: " + key)
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT / "supabase/migrations").glob("*.sql"))}
    if len(actual) != 138 or actual != data["migrations"]:
        raise RuntimeError("Qualified 138-input source inventory differs")
    if any(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
           for path, digest in data["source_sha256"].items()):
        raise RuntimeError("Retained test/runner source binding differs")
    return data


def ui_report(expected: list[str], path: Path, status: int) -> dict[str, object]:
    try:
        report = json.loads(path.read_text())
        cases = [c for s in report["testResults"] for c in s["assertionResults"]]
        names = [c["fullName"].strip() for c in cases]
        bad = [c["fullName"] for c in cases if c["status"] != "passed"]
        accepted = (status == 0 and report["success"] is True and not bad
                    and len(names) == len(set(names)) and set(names) == set(expected))
        return {"accepted": accepted, "expected": expected, "observed": names,
                "nonpassing": bad, "process_exit": status}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"accepted": False, "process_exit": status, "error": str(exc)}


class Runner(financial.Runner):
    def __init__(self) -> None:
        super().__init__("coordinator-gate-evidence")
        self.contract = inputs()
        self.results["gates"] = {}

    def create(self, database: str, template: str = "template0") -> None:
        permitted = (r"f3_report_(?:fresh|upgrade)_ci|"
                     r"ci_coordinator_(?:merchant(?:_review)?|curated)")
        if not re.fullmatch(permitted, database):
            raise RuntimeError("Database outside coordinator-owned namespace")
        self.sql("create-" + database, "postgres",
                 f'CREATE DATABASE "{database}" TEMPLATE "{template}"')
        self.dbs.append(database)

    def qualify(self) -> None:
        _, source = self.command("source", ["git", "rev-parse", "HEAD", "HEAD^{tree}"])
        head, tree = source.splitlines()
        if head != self.env.get("QUALIFICATION_SHA"):
            raise RuntimeError("Checkout differs from the explicit review SHA")
        self.results.update(source_sha=head, source_tree=tree,
                            github_event_sha=self.env.get("GITHUB_SHA"))
        self.command("clean-worktree", ["git", "diff", "--exit-code"])
        self.command("clean-index", ["git", "diff", "--cached", "--exit-code"])
        self.command("candidate-ancestry", ["git", "merge-base", "--is-ancestor",
                                           self.contract["candidate"], "HEAD"])
        _, paths = self.command("published-inputs", ["git", "ls-tree", "-r", "--name-only",
                              self.contract["published"], "supabase/migrations"])
        published = [p for p in paths.splitlines() if p.endswith(".sql")]
        if len(published) != 131:
            raise RuntimeError("Published 131-input inventory differs")
        for path in published:
            _, content = self.command("published-" + Path(path).stem,
                                      ["git", "show", self.contract["published"] + ":" + path])
            if content.encode() != (ROOT / path).read_bytes():
                raise RuntimeError("Published SQL changed: " + path)
        self.output.joinpath("migration-inputs.json").write_text(
            json.dumps(self.contract["migrations"], indent=2) + "\n")
        self.output.joinpath("gate-inputs.json").write_bytes(INPUTS.read_bytes())
        helper = ROOT / "scripts/ci/apply_service_adoption.py"
        self.results["adoption_helper_sha256"] = hashlib.sha256(helper.read_bytes()).hexdigest()
        _, ids = self.command("postgres-containers", ["docker", "ps", "--filter",
                             "ancestor=" + financial.PG_IMAGE, "--format", "{{.ID}}"])
        containers = ids.splitlines()
        if len(containers) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", containers[0]):
            raise RuntimeError("Expected exactly one disposable PostgreSQL service")
        self.pg_container = containers[0]
        _, ports = self.command("postgres-port", ["docker", "port", self.pg_container, "5432/tcp"])
        if not ports.strip() or any(not row.endswith(":54322") for row in ports.splitlines()):
            raise RuntimeError("PostgreSQL service port differs")
        self.command("postgres-image", ["docker", "inspect", "--format", "{{.Image}}",
                                         self.pg_container])
        if self.sql("postgres-version", "postgres", "SHOW server_version_num") != "170006":
            raise RuntimeError("Expected PostgreSQL 17.6")
        self.command("postgrest-pull", ["docker", "pull", financial.REST_IMAGE])
        _, version = self.command("postgrest-version", ["docker", "run", "--rm", "--entrypoint",
                                  "postgrest", financial.REST_IMAGE, "--version"])
        if re.search(r"\b14\.14(?:\b|\.)", version) is None:
            raise RuntimeError("Unexpected PostgREST version")
        self.command("postgrest-image", ["docker", "image", "inspect", financial.REST_IMAGE])

    def replay(self, database: str, *, before_f3: bool = False) -> None:
        self.env["PGDATABASE"] = database
        if before_f3:
            # Keep 120003 helper invocation intact. Copy only a prefix of the exact
            # source inventory; this directory has no linked-project metadata.
            prefix = self.raw / "pre-f3"
            (prefix / "scripts/ci").mkdir(parents=True)
            (prefix / "supabase/migrations").mkdir(parents=True)
            for name in ("migration-replay.sh", "apply_service_adoption.py"):
                shutil.copy2(ROOT / "scripts/ci" / name, prefix / "scripts/ci" / name)
            selected = [n for n in self.contract["migrations"] if n < F3_MIGRATION]
            for name in selected:
                shutil.copy2(ROOT / "supabase/migrations" / name,
                             prefix / "supabase/migrations" / name)
            self.results["pre_f3_inputs"] = {n: self.contract["migrations"][n] for n in selected}
            script = prefix / "scripts/ci/migration-replay.sh"
        else:
            script = ROOT / "scripts/ci/migration-replay.sh"
        self.command("replay-" + database, ["bash", str(script)])
        if self.sql("vector-" + database, database,
                    "SELECT extversion FROM pg_extension WHERE extname='vector'") != "0.8.0":
            raise RuntimeError("Vector fixture qualification differs")

    def roles(self) -> None:
        self.sql("role-provision", "postgres", "CREATE ROLE authenticator LOGIN NOINHERIT "
                 f"NOSUPERUSER NOBYPASSRLS PASSWORD '{self.password}'; "
                 "GRANT anon,authenticated,service_role TO authenticator; "
                 "CREATE ROLE rls_tester NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS; "
                 "GRANT anon,authenticated TO rls_tester;")
        rows = self.sql("role-catalog", "postgres", "SELECT rolname||'|'||rolsuper::text||'|'||"
                        "rolbypassrls::text||'|'||rolinherit::text FROM pg_roles WHERE rolname IN "
                        "('authenticator','rls_tester','anon','authenticated','service_role') "
                        "ORDER BY rolname")
        for name in ("authenticator", "rls_tester", "anon", "authenticated"):
            if name + "|false|false|false" not in rows.splitlines():
                raise RuntimeError("Unexpected browser/test/REST authority")

    @contextlib.contextmanager
    def direct_rest(self, database: str, port: int) -> Iterator[None]:
        if database not in self.dbs or port not in (3006, 3008):
            raise RuntimeError("REST binding is not runner-owned")
        self.bootstrap(database, database)
        _, cid = self.command(database + "-rest-start", ["docker", "run", "-d", "--rm",
            "--network", "host", "--label", "convergeo.disposable=coordinator-ci",
            "-e", f"PGRST_DB_URI=postgresql://authenticator:{self.password}@127.0.0.1:54322/{database}",
            "-e", "PGRST_DB_SCHEMAS=public", "-e", "PGRST_DB_ANON_ROLE=anon",
            "-e", "PGRST_JWT_SECRET=" + self.env["LANE_D_JWT_SECRET"],
            "-e", "PGRST_SERVER_HOST=127.0.0.1", "-e", f"PGRST_SERVER_PORT={port}",
            financial.REST_IMAGE])
        cid = cid.strip()
        if not re.fullmatch(r"[a-f0-9]{64}", cid):
            raise RuntimeError("Invalid newly created REST container identity")
        with contextlib.ExitStack() as cleanup:
            cleanup.callback(self.command, database + "-rest-stop", ["docker", "rm", "-f", cid])
            cleanup.callback(self.command, database + "-rest-logs", ["docker", "logs", cid])
            deadline = time.monotonic() + 45
            while True:
                try:
                    self.probe(port, database)
                    break
                except (OSError, RuntimeError) as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("REST binding readiness failed") from exc
                    time.sleep(0.25)
            yield

    def probe(self, port: int, database: str) -> None:
        # http.client never follows redirects or uses proxy settings. Verify exact
        # SQL/HTTP row binding and denial cells, not merely a listening socket.
        path = "/ci_critical_binding_probe?select=group_name,database_name"
        for role in ("service_role", "anon", "authenticated", "invalid"):
            token = ("invalid.invalid.invalid" if role == "invalid" else
                     role_token(role, self.env["LANE_D_JWT_SECRET"]))
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                connection.request("GET", path, headers={"Authorization": "Bearer " + token})
                response = connection.getresponse()
                body = response.read(65537)
                if role == "service_role":
                    if response.status != 200 or len(body) > 65536 or json.loads(body) != [
                        {"group_name": database, "database_name": database}
                    ]:
                        raise RuntimeError("REST database row binding differs")
                elif response.status not in ((401,) if role == "invalid" else (401, 403)):
                    raise RuntimeError("Browser/invalid JWT read the service-only probe")
            finally:
                connection.close()

    def test_gate(self, label: str, selectors: list[str],
                  expected: list[str] | None = None) -> bool:
        collection_exit, text = self.pytest(label + "-collection", selectors, collect=True)
        observed = financial.nodes_from_collection(text)
        financial.require_collection(expected or observed, observed, collection_exit)
        expected = expected or observed
        self.output.joinpath(label + "-expected.json").write_text(json.dumps(expected, indent=2))
        status, _ = self.pytest(label, selectors)
        result, accepted = financial.load_reporter()._reconcile(
            expected, self.output / (label + ".xml"), status)
        gates = self.results["gates"]
        assert isinstance(gates, dict)
        gates[label] = result
        self.write_result()
        return bool(accepted)

    def f3(self) -> None:
        fresh, upgrade = "f3_report_fresh_ci", "f3_report_upgrade_ci"
        self.create(fresh)
        self.replay(fresh)
        self.roles()
        self.create(upgrade)
        self.replay(upgrade, before_f3=True)
        if self.sql("pre-f3-absent", upgrade,
                    "SELECT to_regclass('public.reconciliation_report_versions')::text"):
            raise RuntimeError("F3 upgrade schema must precede the report-version migration")
        self.bind(fresh)
        self.env.update(F3_REPORT_DATABASE=fresh, F3_DISPOSABLE_REPORT_DB="1",
            F3_REPORT_UPGRADE_DATABASE=upgrade,
            F3_REPORT_UPGRADE_DB_URL=f"postgresql://postgres:postgres@127.0.0.1:54322/{upgrade}",
            F3_REPORT_UPGRADE_POSTGREST_URL="http://127.0.0.1:3008")
        with self.direct_rest(fresh, 3006), self.direct_rest(upgrade, 3008):
            accepted = self.test_gate("f3-seven",
                ["tests/real_stack/f3_reconciliation_real_stack.py"], self.contract["f3"])
        # The seventh unchanged test inserts legacy bytes before applying170000.
        # Capture its surviving row then apply only the remaining ordered suffix.
        if not accepted:
            raise RuntimeError("F3 seven mandatory identities did not all pass")
        legacy_query = ("SELECT row_to_json(r)::text FROM public.reconciliation_reports r "
                        "ORDER BY id")
        before = self.sql("legacy-after-f3", upgrade, legacy_query)
        if not before:
            raise RuntimeError("Upgrade test did not retain legacy report evidence")
        for name in self.contract["migrations"]:
            if name > F3_MIGRATION:
                self.command("upgrade-tail-" + Path(name).stem, ["psql", "-X", "-v",
                    "ON_ERROR_STOP=1", "-d", upgrade, "-f",
                    str(ROOT / "supabase/migrations" / name)])
        after = self.sql("legacy-after-full-upgrade", upgrade, legacy_query)
        if before != after:
            raise RuntimeError("Full upgrade changed preserved legacy bytes")

    def merchant(self) -> None:
        database = "ci_coordinator_merchant"
        self.create(database)
        self.replay(database)
        self.bind(database)
        self.env["MERCHANT_STOCK_ISOLATED_DB"] = "1"
        self.bootstrap(database, database)
        if not self.test_gate("merchant-db", ["tests/test_vendor_stock_adjustment_db.py",
                              "tests/test_location_stock.py"], self.contract["db"]):
            raise RuntimeError("Merchant 26 DB identities incomplete")
        # Keep independent regression fixtures below real admission caps.
        review_database = "ci_coordinator_merchant_review"
        self.create(review_database)
        self.replay(review_database)
        self.bind(review_database)
        self.bootstrap(review_database, review_database)
        if not self.test_gate("merchant-review-db",
                              ["tests/test_merchant_review_boundaries_db.py"],
                              self.contract["review_db"]):
            raise RuntimeError("Merchant review database regressions incomplete")
        if not self.test_gate("merchant-normal", self.contract["normal_selectors"],
                              self.contract["normal"]):
            raise RuntimeError("Merchant 267 compatibility identities incomplete")
        _, version = self.command("node-version", ["node", "-p", "process.versions.node"])
        _, pnpm = self.command("pnpm-version", ["pnpm", "--version"])
        if version.split(".")[0] != "22" or pnpm.strip() != "9.15.4":
            raise RuntimeError("Mounted acceptance requires pinned Node22/pnpm9.15.4")
        path = self.raw / "mounted.json"
        status, _ = self.command("merchant-mounted", ["pnpm", "--filter", "vendor", "exec",
            "vitest", "run", *[p.removeprefix("apps/vendor/") for p in self.contract["ui_files"]],
            "--reporter=json", "--outputFile=" + str(path)], checked=False)
        result = ui_report(self.contract["ui"], path, status)
        if path.is_file():
            self.output.joinpath("mounted.json").write_text(self.redact(path.read_text()))
        gates = self.results["gates"]
        assert isinstance(gates, dict)
        gates["merchant-mounted"] = result
        self.write_result()
        if result["accepted"] is not True:
            raise RuntimeError("Six mounted UI identities incomplete")
        self.results["integrated_vendor_buyer_journey"] = "NOT_RUN"

    def curated(self) -> None:
        database = "ci_coordinator_curated"
        self.create(database)
        self.replay(database)
        self.roles()
        self.bind(database)
        self.env["SUPABASE_REST_URL"] = "http://127.0.0.1:3006"
        with self.direct_rest(database, 3006):
            # Readiness already proved this runner-owned row over SQL and HTTP.
            # Remove instrumentation before the unchanged full-table RLS gate;
            # do not exempt unknown tables or alter its expected authorities.
            self.sql("remove-owned-probe-before-rls", database,
                     "DROP TABLE public.ci_critical_binding_probe")
            # Run both gates even if curated execution fails; retain both failures.
            curated = self.test_gate("curated", self.contract["curated"])
            rls = self.test_gate("rls", ["tests/rls"])
        if not curated or not rls:
            raise RuntimeError("Full curated/RLS gates incomplete (zero skips required)")

    def execute_gate(self, gate: str) -> None:
        self.qualify()
        getattr(self, gate)()
        self.results["accepted"] = not any(self.steps.values())

    def finish(self) -> None:
        if hasattr(self, "pg_container"):
            try:
                self.command("postgres-logs", ["docker", "logs", self.pg_container])
            except Exception as exc:
                self.results.update(accepted=False, log_error=self.redact(str(exc)))
        super().finish()
        shutil.rmtree(self.raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=("f3", "merchant", "curated"))
    args = parser.parse_args()
    financial.validate_host()  # Fail before allocating or contacting resources.
    runner = Runner()
    runner.results["gate"] = args.gate
    try:
        runner.execute_gate(args.gate)
    except Exception as exc:
        runner.results.update(accepted=False, error=runner.redact(str(exc)))
    finally:
        runner.finish()
    return 0 if runner.results["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
