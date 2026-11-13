"""SYNTHETIC ONLY catalog, rollback, crash/retry and ledger controls on owned PG.

Creates uniquely named databases, replays the real 127-input baseline and three
F2 prerequisites, then exercises the immutable adoption boundary. Never contacts
a hosted database, runs a provider call, or deletes a pre-existing database.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import apply_service_adoption as adoption
import apply_service_adoption_disposable as installer

ROOT = installer.ROOT
MIGRATIONS = ROOT / "supabase/migrations"
TABLES = (
    "payments",
    "payment_collection_receipts",
    "ledger_transactions",
    "ledger_postings",
    "orders",
    "order_items",
    "order_item_services",
    "checkout_groups",
    "jobs",
    "job_quotes",
    "audit_log",
    "service_payment_obligations",
    "ledger_accounts",
)


class Rehearsal:
    def __init__(self, evidence: Path) -> None:
        installer.fixture_binding()
        if evidence.exists():
            raise ValueError("Refusing to replace prior rehearsal evidence")
        evidence.mkdir(parents=True)
        self.evidence = evidence
        self.namespace = uuid4().hex[:12]
        self.history = installer.history_rows(MIGRATIONS)
        self.history_by_version = {row["version"]: row for row in self.history}
        self.created: list[str] = []
        self.fixtures: list[dict[str, Any]] = []
        self.checks: list[dict[str, Any]] = []
        self.env = os.environ.copy()
        for key in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGOPTIONS"):
            self.env.pop(key, None)
        self.env.update(
            PGHOST="127.0.0.1", PGPORT="54322", PGUSER="postgres", PGPASSWORD="postgres"
        )

    def args(self, database: str, *, atomic: bool = False) -> list[str]:
        if database != "postgres" and database not in self.created:
            raise ValueError("Database not created by this rehearsal")
        return [
            "psql",
            "-X",
            "-h",
            "127.0.0.1",
            "-p",
            "54322",
            "-U",
            "postgres",
            "-d",
            database,
            "-Atq",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=verbose",
            *(["--single-transaction"] if atomic else []),
        ]

    def run(
        self, database: str, sql: str, name: str, *, atomic: bool = False, expected: int = 0
    ) -> str:
        proc = subprocess.run(
            self.args(database, atomic=atomic),
            input=sql,
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
            timeout=180,
        )
        (self.evidence / (name + ".log")).write_text(proc.stdout + proc.stderr)
        with (self.evidence / "commands.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "name": name,
                        "database": database,
                        "arguments": self.args(database, atomic=atomic),
                        "exit": proc.returncode,
                    }
                )
                + "\n"
            )
        if (expected == 0 and proc.returncode != 0) or (expected != 0 and proc.returncode == 0):
            raise RuntimeError(f"{name}: unexpected exit {proc.returncode}; retained log")
        return proc.stdout + proc.stderr if expected else proc.stdout.strip()

    def query(self, database: str, sql: str) -> Any:
        raw = self.run(database, sql, "query-" + uuid4().hex[:8])
        return json.loads(raw)

    def create(self, label: str, *, template: str | None = None) -> str:
        name = f"ci_adoption_{self.namespace}_{label}"
        if not installer.DATABASE_RE.fullmatch(name):
            raise ValueError("Invalid owned database name")
        if template is not None and template not in self.created:
            raise ValueError("Template not owned by this rehearsal")
        self.run(
            "postgres",
            f'CREATE DATABASE "{name}" TEMPLATE "{template or "template0"}";',
            "create-" + label,
        )
        self.created.append(name)
        self.run(
            "postgres",
            f'COMMENT ON DATABASE "{name}" IS '
            + installer.literal(installer.MARKER_PREFIX + name)
            + ";",
            "mark-" + label,
        )
        return name

    def snapshot(self, database: str) -> dict[str, Any]:
        catalog = self.query(database, installer.catalog_sql() + ";")
        data = {}
        for table in (*TABLES, "supabase_migrations.schema_migrations"):
            qualified = table if "." in table else "public." + table
            value = (
                "to_jsonb(t) || jsonb_build_object("
                "'statements_bounds',array_dims(t.statements),"
                "'rollback_bounds',array_dims(t.rollback))"
                if table == "supabase_migrations.schema_migrations" else "to_jsonb(t)"
            )
            ordering = "t.version" if table == "supabase_migrations.schema_migrations" else "to_jsonb(t)::text"
            data[qualified] = self.query(
                database,
                f"SELECT coalesce(jsonb_agg({value} ORDER BY {ordering}),'[]'::jsonb) "
                f"FROM {qualified} t;",
            )
        ledger_bytes = self.query(
            database,
            "SELECT coalesce(jsonb_agg(jsonb_build_object("
            "'version',version,'statements',encode(array_send(statements),'hex'),"
            "'rollback',encode(array_send(rollback),'hex')) ORDER BY version),"
            "'[]'::jsonb) FROM supabase_migrations.schema_migrations;",
        )
        return {"catalog": catalog, "data": data, "ledger_bytes": ledger_bytes}

    def bind(self, database: str) -> dict[str, Any]:
        bound = installer.plan(database, installer.MARKER_PREFIX + database, MIGRATIONS)
        (self.evidence / (database + "-plan.json")).write_text(json.dumps(bound, indent=2) + "\n")
        return bound

    def save(self, name: str, before: Any, after: Any, *, assertions: list[str]) -> None:
        payload = {
            "name": name,
            "status": "PASS",
            "assertions": assertions,
            "before": before,
            "after": after,
        }
        (self.evidence / (name + "-evidence.json")).write_text(json.dumps(payload, indent=2) + "\n")
        self.checks.append({"name": name, "status": "PASS", "assertions": assertions})
        print(name + " PASS", flush=True)

    def apply_recorded(self, database: str, path: Path) -> None:
        version, _name = path.stem.split("_", 1)
        original = path.read_text()
        record = installer.history_insert(self.history_by_version[version])
        # Historical inputs without their own BEGIN are recorded atomically by
        # --single-transaction. Files with BEGIN/COMMIT retain their exact bytes;
        # prefix preparation is disposable only, not a proposed shared installer.
        self.run(database, original + "\n" + record, "replay-" + version, atomic=True)

    def seed(self, database: str) -> None:
        # Reuse existing native SQL fixture code; obligations=False has no HTTP
        # branch. Bind its connection before importing application/test modules.
        os.environ["SUPABASE_DB_URL"] = "postgresql://postgres:postgres@127.0.0.1:54322/" + database
        os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dev")
        os.environ.setdefault("SUPABASE_ANON_KEY", "dev")
        sys.path.insert(0, str(ROOT / "services/api"))
        sys.path.insert(0, str(ROOT / "scripts/drills"))
        from f2_upgrade_probe import fingerprint, sql
        from tests.lane_d.test_f2_service_funding_postgrest import seed

        shared = None
        for kind in (
            "pending",
            "receipt",
            "card",
            "ambiguous",
            "healthy",
            "shared_primary",
            "shared_secondary",
            "foreign_balance",
        ):
            fixture = seed(obligations=False)
            if kind == "shared_primary":
                shared = fixture
            elif kind == "shared_secondary":
                assert shared is not None
                sql(f"""BEGIN;
                  UPDATE public.orders SET customer_id='{shared["buyer"]}',
                    checkout_group_id='{shared["checkout"]}' WHERE id='{fixture["order"]}';
                  UPDATE public.jobs SET customer_id='{shared["buyer"]}'
                    WHERE id='{fixture["job"]}'; COMMIT;""")
                fixture["buyer"], fixture["checkout"] = shared["buyer"], shared["checkout"]
            elif kind == "foreign_balance":
                sql(f"""INSERT INTO public.checkout_groups(customer_id,idempotency_key,
                  subtotal_ngwee,delivery_fee_ngwee,total_ngwee,status)
                  VALUES ('{fixture["buyer"]}','service-balance-{fixture["order"]}',
                    70000,0,70000,'pending');""")
            payment = str(uuid4())
            reference = f"f2-upgrade-{payment}"
            rail = "card" if kind == "card" else "mtn"
            sql(f"""INSERT INTO public.payments
              (id,checkout_group_id,provider,rail,lenco_reference,amount_ngwee,status,raw)
              VALUES ('{payment}','{fixture["checkout"]}','lenco','{rail}',
                '{reference}',30000,'initiated','{{}}');""")
            if kind in {"receipt", "card"}:
                result = sql(f"""SELECT public.apply_prepaid_collection_success(
                  '{payment}','{fixture["buyer"]}','F2 synthetic baseline upgrade',
                  '{{"reference":"{reference}","currency":"ZMW","amount_ngwee":30000,
                    "provider_reference":"synthetic-{payment}","source":"f2_upgrade_fixture"}}'
                  ::jsonb)::text;""")
                if json.loads(result[0])["result"] != "applied":
                    raise RuntimeError("Baseline fixture settlement did not apply")
            if kind == "ambiguous":
                sql(
                    "UPDATE public.orders SET commission_snapshot='{}' "
                    f"WHERE id='{fixture['order']}'"
                )
            self.fixtures.append({"kind": kind, "payment": payment, **fixture})
        # Fingerprint after all sharing changes, using the preserved probe's
        # own exact monetary evidence query, then full row comparison below.
        for fixture in self.fixtures:
            fixture["monetary_before"] = fingerprint(fixture["order"], fixture["payment"])
        (self.evidence / "eight-legacy-fixtures.json").write_text(
            json.dumps(self.fixtures, indent=2) + "\n"
        )

    def seed_foreign_obligation(self, database: str) -> None:
        os.environ["SUPABASE_DB_URL"] = "postgresql://postgres:postgres@127.0.0.1:54322/" + database
        from f2_upgrade_probe import sql
        from tests.lane_d.test_f2_service_funding_postgrest import seed

        foreign = seed(obligations=False)
        sql(
            f"SELECT public.create_service_payment_obligations('{foreign['order']}',"
            f"'{foreign['job']}','{foreign['buyer']}',100000,30000);"
        )
        target = seed(obligations=False)
        sql(f"""BEGIN;
          UPDATE public.orders SET customer_id='{foreign["buyer"]}',
            checkout_group_id='{foreign["checkout"]}' WHERE id='{target["order"]}';
          UPDATE public.jobs SET customer_id='{foreign["buyer"]}'
            WHERE id='{target["job"]}'; COMMIT;""")
        self.foreign, self.foreign_target = foreign, target
        (self.evidence / "foreign-obligation-fixtures.json").write_text(
            json.dumps({"foreign": foreign, "target": target}, indent=2) + "\n"
        )

    def baseline(self) -> str:
        database = self.create("template")
        script = (ROOT / "scripts/ci/migration-replay.sh").read_text()
        shim = script.split("<<'SQL'\n", 1)[1].split("\nSQL\n", 1)[0]
        self.run(database, shim, "supabase-shim", atomic=True)
        self.run(
            database,
            """CREATE SCHEMA supabase_migrations;
          CREATE TABLE supabase_migrations.schema_migrations (
            version text NOT NULL PRIMARY KEY, statements text[], name text,
            created_by text, idempotency_key text UNIQUE, rollback text[]);
          REVOKE ALL ON SCHEMA supabase_migrations FROM PUBLIC,anon,authenticated;
          REVOKE ALL ON supabase_migrations.schema_migrations FROM PUBLIC,anon,authenticated;
        """,
            "fixture-ledger",
            atomic=True,
        )
        paths = sorted(MIGRATIONS.glob("*.sql"))
        for path in paths:
            if path.name >= adoption.AUTHORITY:
                break
            self.apply_recorded(database, path)
        print("127-input real baseline replayed", flush=True)
        self.seed(database)
        for path in paths:
            if adoption.AUTHORITY <= path.name < adoption.ADOPTION:
                self.apply_recorded(database, path)
        self.seed_foreign_obligation(database)
        runtime = self.query(
            database,
            """SELECT jsonb_build_object(
          'postgres',version(),'server_version_num',current_setting('server_version_num'),
          'vector',(SELECT extversion FROM pg_extension WHERE extname='vector'),
          'fixture_ledger_columns',(SELECT jsonb_agg(jsonb_build_array(attname,
            format_type(atttypid,atttypmod)) ORDER BY attnum) FROM pg_attribute
            WHERE attrelid='supabase_migrations.schema_migrations'::regclass
            AND attnum>0 AND NOT attisdropped));""",
        )
        if runtime["server_version_num"] != "170006" or runtime["vector"] != "0.8.0":
            raise RuntimeError("Unqualified local fixture runtime")
        (self.evidence / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
        return database

    def catalog_challenges(self, template: str) -> None:
        signature = installer.SIGNATURE
        alterations = {
            "security_invoker": f"ALTER FUNCTION {signature} SECURITY INVOKER;",
            "search_path": f"ALTER FUNCTION {signature} SET search_path=public;",
            "public_execute": f"GRANT EXECUTE ON FUNCTION {signature} TO PUBLIC;",
            "authenticated_execute": f"GRANT EXECUTE ON FUNCTION {signature} TO authenticated;",
            "service_grant_option": (
                f"GRANT EXECUTE ON FUNCTION {signature} TO service_role WITH GRANT OPTION;"
            ),
            "service_execute_missing": f"REVOKE EXECUTE ON FUNCTION {signature} FROM service_role;",
            "strict": f"ALTER FUNCTION {signature} STRICT;",
            "leakproof": f"ALTER FUNCTION {signature} LEAKPROOF;",
            "volatility": f"ALTER FUNCTION {signature} STABLE;",
            "parallel": f"ALTER FUNCTION {signature} PARALLEL SAFE;",
        }
        original_source = (MIGRATIONS / adoption.AUTHORITY).read_text()
        start = original_source.index("create function public.create_service_payment_obligations(")
        end = original_source.index("\ncreate function public.record_collection_failure", start)
        original = original_source[start:end].replace(
            "create function", "create or replace function", 1
        )
        alterations["body_drift"] = original.replace(
            "declare o public.orders%rowtype; balance_checkout uuid;",
            "declare o public.orders%rowtype; balance_checkout uuid; -- deliberate body challenge",
        )
        for name, alteration in alterations.items():
            database = self.create(name, template=template)
            untouched = self.snapshot(database)
            self.run(database, alteration, "alter-" + name)
            before = self.snapshot(database)
            if name != "body_drift":
                assert (
                    before["catalog"]["pg_proc"]["prosrc"]
                    == untouched["catalog"]["pg_proc"]["prosrc"]
                )
            bound = self.bind(database)
            text = self.run(
                database,
                installer.render(bound, MIGRATIONS),
                "reject-" + name,
                atomic=True,
                expected=1,
            )
            assert "Service obligation authority" in text
            after = self.snapshot(database)
            assert before == after, (
                name + " changed catalog, economic evidence or ledger on rejection"
            )
            self.save(
                name,
                before,
                after,
                assertions=[
                    "actual installed catalog challenge rejected before adoption",
                    "catalog/body/owner/ACL, all economic rows and history "
                    "identical after connection exit",
                    "body bytes retained for every metadata-only challenge",
                ],
            )

    def verify_success(self, before: dict[str, Any], after: dict[str, Any]) -> None:
        assert before["catalog"] == after["catalog"], "Authority catalog changed"
        assert after["ledger_bytes"][:len(before["ledger_bytes"])] == before["ledger_bytes"], (
            "Previously installed array bytes changed"
        )
        assert after["data"]["supabase_migrations.schema_migrations"][
            :len(before["data"]["supabase_migrations.schema_migrations"])
        ] == before["data"]["supabase_migrations.schema_migrations"], (
            "Previously installed six-column history changed"
        )
        for table in TABLES:
            key = "public." + table
            if table not in {"checkout_groups", "service_payment_obligations", "audit_log"}:
                assert before["data"][key] == after["data"][key], (
                    "Economic evidence changed: " + table
                )
        previous_checkouts = {row["id"]: row for row in before["data"]["public.checkout_groups"]}
        current_checkouts = {row["id"]: row for row in after["data"]["public.checkout_groups"]}
        assert all(current_checkouts[key] == row for key, row in previous_checkouts.items())
        previous_audit = {row["id"]: row for row in before["data"]["public.audit_log"]}
        current_audit = {row["id"]: row for row in after["data"]["public.audit_log"]}
        assert all(current_audit[key] == row for key, row in previous_audit.items())
        obligations = after["data"]["public.service_payment_obligations"]
        holds = [
            row
            for row in current_audit.values()
            if row["action"] == "service.obligation_adoption_held"
        ]
        held_kinds = {"ambiguous", "shared_primary", "shared_secondary", "foreign_balance"}
        for fixture in self.fixtures:
            own = [row for row in obligations if row["order_id"] == fixture["order"]]
            own_holds = [row for row in holds if row["entity_id"] == fixture["order"]]
            if fixture["kind"] in held_kinds:
                assert own == [] and len(own_holds) == 1
            else:
                assert len(own) == 2 and {row["leg"] for row in own} == {"deposit", "balance"}
                assert own_holds == []
        foreign_before = [
            row
            for row in before["data"]["public.service_payment_obligations"]
            if row["order_id"] == self.foreign["order"]
        ]
        assert foreign_before == [
            row for row in obligations if row["order_id"] == self.foreign["order"]
        ]
        assert not any(row["order_id"] == self.foreign_target["order"] for row in obligations)
        foreign_holds = [row for row in holds if row["entity_id"] == self.foreign_target["order"]]
        assert len(foreign_holds) == 1
        assert foreign_holds[0]["after"]["reason"] == "checkout_linked_to_other_obligation"
        # Exactly the original DO bytes, never the temporary creator/wrapper,
        # are recorded in the authoritative Supabase-compatible row.
        ledger = after["data"]["supabase_migrations.schema_migrations"]
        adoption_rows = [row for row in ledger if row["version"] == installer.VERSION]
        assert len(adoption_rows) == 1
        assert adoption_rows[0] == self.history_by_version[installer.VERSION]
        assert len(ledger) == len(before["data"]["supabase_migrations.schema_migrations"]) + 1

    def success_and_resume(self, template: str, *, owner: bool = False) -> None:
        name = "different_owner" if owner else "success_resume"
        database = self.create(name, template=template)
        if owner:
            self.run(
                database,
                f"ALTER FUNCTION {installer.SIGNATURE} OWNER TO supabase_admin;",
                "different-owner",
            )
        before = self.snapshot(database)
        bound = self.bind(database)
        command = [
            sys.executable,
            str(Path(installer.__file__)),
            "--plan",
            str(self.evidence / (database + "-plan.json")),
            "--execute-disposable",
        ]
        actual = subprocess.run(command, text=True, capture_output=True, env=self.env, check=False)
        (self.evidence / (name + "-actual-installer.log")).write_text(actual.stdout + actual.stderr)
        assert actual.returncode == 0, "Actual disposable installer failed: " + name
        assert "ADOPTION_APPLIED_AND_RECORDED_ATOMICALLY" in actual.stdout
        after = self.snapshot(database)
        self.verify_success(before, after)
        text = self.run(
            database, installer.render(bound, MIGRATIONS), name + "-resume", atomic=True
        )
        assert "ADOPTION_RESUMED_NO_SQL_REEXECUTION" in text
        resumed = self.snapshot(database)
        assert after == resumed
        self.save(
            name,
            before,
            after,
            assertions=[
                "actual installer transaction applied and recorded original 120003 exactly once",
                "all eight legacy fixtures and foreign obligation evidence preserved",
                "one durable hold per ambiguous order; no fabricated canonical card proof",
                "full routine OID/signature/body/owner/execution metadata/grantor ACL restored",
                "lost-response style repeat resumes without second raw adoption "
                "or data/history changes",
            ],
        )

    def injected_failure(self, template: str, name: str, boundary: str, *, crash: bool) -> None:
        database = self.create(name, template=template)
        before = self.snapshot(database)
        bound = self.bind(database)
        assert_writes = """DO $writes_check$ BEGIN
          IF (SELECT count(*) FROM public.service_payment_obligations)<=2
             OR (SELECT count(*) FROM public.audit_log
                 WHERE action='service.obligation_adoption_held')<5 THEN
            RAISE EXCEPTION 'Fault insertion did not follow actual partial adoption';
          END IF;
        END; $writes_check$;\n"""
        fault = assert_writes + (
            "SELECT pg_sleep(30);\n"
            if crash
            else "DO $forced_failure$ BEGIN RAISE EXCEPTION "
            "'deliberate adoption rollback challenge'; END; $forced_failure$;\n"
        )
        sql = installer.render(bound, MIGRATIONS).replace(boundary, boundary + "\n" + fault)
        if crash:
            env = dict(self.env, PGAPPNAME="adoption-rehearsal-" + self.namespace + "-" + name)
            proc = subprocess.Popen(
                self.args(database, atomic=True),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            assert proc.stdin is not None
            proc.stdin.write(sql)
            proc.stdin.close()
            deadline = time.monotonic() + 15
            backend = None
            try:
                while time.monotonic() < deadline:
                    found = self.query(
                        "postgres",
                        "SELECT coalesce(jsonb_agg(pid),'[]'::jsonb) "
                        "FROM pg_stat_activity WHERE application_name="
                        + installer.literal(env["PGAPPNAME"])
                        + " AND wait_event='PgSleep';",
                    )
                    if found:
                        assert len(found) == 1
                        backend = found[0]
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if backend is None:
                    raise RuntimeError(
                        "Owned backend did not reach the deliberate post-write crash boundary"
                    )
                result = self.query(
                    "postgres", f"SELECT to_jsonb(pg_terminate_backend({backend}));"
                )
                assert result is True
                assert proc.stdout is not None and proc.stderr is not None
                stdout, stderr = proc.stdout.read(), proc.stderr.read()
                status = proc.wait(timeout=15)
                (self.evidence / (name + ".log")).write_text(stdout + stderr)
                assert status != 0
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
        else:
            text = self.run(database, sql, name, atomic=True, expected=1)
            assert "deliberate adoption rollback challenge" in text
        after = self.snapshot(database)
        assert before == after, "Partial adoption/catalog/history survived failed transaction"
        self.save(
            name,
            before,
            after,
            assertions=[
                "fault reached after actual obligation/hold writes",
                "independent post-connection catalog/data/history fingerprint "
                "exactly equals pre-transaction state",
                "no swallowed 23505, no partial money/DDL/hold/ledger row",
            ],
        )
        # Resume the identical approved local plan after a failure, then verify
        # actual full adoption rather than merely proving a no-op retry.
        self.run(database, installer.render(bound, MIGRATIONS), name + "-retry", atomic=True)
        self.verify_success(before, self.snapshot(database))

    def concurrent_resume(self, template: str) -> None:
        database = self.create("concurrent", template=template)
        before = self.snapshot(database)
        bound = self.bind(database)
        sql = installer.render(bound, MIGRATIONS)
        processes = [
            subprocess.Popen(
                self.args(database, atomic=True),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.env,
            )
            for _ in range(2)
        ]
        for proc in processes:
            assert proc.stdin is not None
            proc.stdin.write(sql)
            proc.stdin.close()
        outputs = []
        for index, proc in enumerate(processes):
            assert proc.stdout is not None and proc.stderr is not None
            text = proc.stdout.read() + proc.stderr.read()
            assert proc.wait(timeout=30) == 0
            (self.evidence / (f"concurrent-{index}.log")).write_text(text)
            outputs.append(text)
        assert sum("ADOPTION_APPLIED_AND_RECORDED_ATOMICALLY" in text for text in outputs) == 1
        assert sum("ADOPTION_RESUMED_NO_SQL_REEXECUTION" in text for text in outputs) == 1
        after = self.snapshot(database)
        self.verify_success(before, after)
        self.save(
            "concurrent_resume",
            before,
            after,
            assertions=[
                "two actual wrapper connections serialize under the transaction history lock",
                "one application and one resume; original adoption executed once",
                "exact final ledger row, catalog restoration and eight-fixture conservation",
            ],
        )

    def history_rejection(self, template: str, *, marker: bool = False) -> None:
        name = "marker_mismatch" if marker else "history_mismatch"
        database = self.create(name, template=template)
        bound = self.bind(database)
        if marker:
            self.run(
                "postgres", f"COMMENT ON DATABASE \"{database}\" IS 'unowned';", name + "-alter"
            )
        else:
            self.run(
                database,
                "UPDATE supabase_migrations.schema_migrations "
                "SET statements=ARRAY['unexecuted bogus SQL'] "
                "WHERE version='20260929120000';",
                name + "-alter",
            )
        before = self.snapshot(database)
        text = self.run(
            database, installer.render(bound, MIGRATIONS), name + "-reject", atomic=True, expected=1
        )
        assert ("Refusing non-owned" if marker else "Installed history differs") in text
        after = self.snapshot(database)
        assert before == after
        self.save(
            name,
            before,
            after,
            assertions=[
                "non-owned marker or non-equivalent installed history fails closed",
                "no authority replacement, adoption or migration-history repair occurred",
            ],
        )

    def six_column_history_rejections(self, template: str) -> None:
        """Challenge each new metadata field, array bounds, and unique constraint."""
        challenges = (
            ("statement_bounds", "UPDATE supabase_migrations.schema_migrations "
             "SET statements=ARRAY[statements[0]] WHERE version='0003';", "Installed history differs"),
            ("rollback_bounds", "UPDATE supabase_migrations.schema_migrations "
             "SET rollback=ARRAY[rollback[-2]] WHERE version='0003';", "Installed history differs"),
            ("rollback_value", "UPDATE supabase_migrations.schema_migrations "
             "SET rollback=NULL WHERE version='0002';", "Installed history differs"),
            ("created_by", "UPDATE supabase_migrations.schema_migrations "
             "SET created_by='synthetic-drift' WHERE version='0002';", "Installed history differs"),
            ("idempotency_key", "UPDATE supabase_migrations.schema_migrations "
             "SET idempotency_key='synthetic-drift' WHERE version='0002';", "Installed history differs"),
            ("unique_constraint", "ALTER TABLE supabase_migrations.schema_migrations "
             "DROP CONSTRAINT schema_migrations_idempotency_key_key;", "Unreviewed migration ledger schema"),
        )
        for label, alteration, expected in challenges:
            database = self.create("history_" + label, template=template)
            bound = self.bind(database)
            self.run(database, alteration, label + "-alter")
            before = self.snapshot(database)
            output = self.run(database, installer.render(bound, MIGRATIONS),
                              label + "-reject", atomic=True, expected=1)
            assert expected in output
            after = self.snapshot(database)
            assert before == after, label + " changed history or catalog on rejection"
            self.save("history_" + label, before, after, assertions=[
                "six-column history or array shape drift fails before adoption",
                "atomic failure preserves exact metadata and array_send bytes",
            ])
        database = self.create("history_duplicate_key", template=template)
        before = self.snapshot(database)
        output = self.run(database,
            "INSERT INTO supabase_migrations.schema_migrations "
            "(version,statements,name,created_by,idempotency_key,rollback) "
            "SELECT '99999999999999',statements,name,created_by,idempotency_key,rollback "
            "FROM supabase_migrations.schema_migrations WHERE version='0002';",
            "duplicate-idempotency-reject", atomic=True, expected=1)
        assert "23505" in output
        after = self.snapshot(database)
        assert before == after
        self.save("history_duplicate_key", before, after, assertions=[
            "unique idempotency_key rejects duplicate synthetic history",
            "failed insert leaves all six columns and array bytes unchanged",
        ])

    def raw_collision(self, template: str) -> None:
        database = self.create("raw_collision", template=template)
        before = self.snapshot(database)
        error = self.run(
            database,
            (MIGRATIONS / adoption.ADOPTION).read_text(),
            "raw-immutable-adoption",
            atomic=True,
            expected=1,
        )
        assert "23505" in error, "Original immutable adoption did not reproduce the real collision"
        after = self.snapshot(database)
        assert before == after
        self.save(
            "raw_collision",
            before,
            after,
            assertions=[
                "actual immutable DO reproduced SQLSTATE 23505 "
                "against shared/foreign checkout seeds",
                "failed raw adoption rolled back all attempted money/metadata "
                "and recorded no history",
            ],
        )

    def resume_metadata_rejection(self, template: str) -> None:
        database = self.create("resume_catalog_drift", template=template)
        bound = self.bind(database)
        self.run(database, installer.render(bound, MIGRATIONS), "resume-catalog-first", atomic=True)
        self.run(
            database,
            f"ALTER FUNCTION {installer.SIGNATURE} SECURITY INVOKER;",
            "resume-catalog-alter",
        )
        before = self.snapshot(database)
        error = self.run(
            database,
            installer.render(bound, MIGRATIONS),
            "resume-catalog-reject",
            atomic=True,
            expected=1,
        )
        assert "Service obligation authority metadata differs" in error
        after = self.snapshot(database)
        assert before == after
        self.save(
            "resume_metadata_rejection",
            before,
            after,
            assertions=[
                "resume validates installed authority "
                "even when original adoption ledger row exists",
                "metadata drift fails closed without replacing newer authority "
                "or re-executing adoption",
            ],
        )

    def full_history_resume(self, template: str) -> None:
        database = self.create("complete_history", template=template)
        bound = self.bind(database)
        before = self.snapshot(database)
        self.run(
            database, installer.render(bound, MIGRATIONS), "full-history-boundary", atomic=True
        )
        self.verify_success(before, self.snapshot(database))
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name > adoption.ADOPTION:
                self.apply_recorded(database, path)
        completed = self.snapshot(database)
        pending = self.query(
            database,
            "SELECT to_jsonb(NOT EXISTS(SELECT 1 "
            "FROM supabase_migrations.schema_migrations WHERE version="
            + installer.literal(installer.VERSION)
            + "));",
        )
        assert pending is False
        text = self.run(
            database, installer.render(bound, MIGRATIONS), "full-history-resume", atomic=True
        )
        assert "ADOPTION_RESUMED_NO_SQL_REEXECUTION" in text
        resumed = self.snapshot(database)
        assert completed == resumed
        actual = completed["data"]["supabase_migrations.schema_migrations"]
        assert sorted(actual, key=lambda row: row["version"]) == self.history
        self.save(
            "full_history_resume",
            completed,
            resumed,
            assertions=[
                "entire current ordered migration inventory executed "
                "on disposable realistic history",
                "migration-membership selection excludes 120003 after the atomic boundary",
                "repeat against completed ledger resumes without second raw adoption "
                "or changed rows/catalog",
            ],
        )

    def cleanup(self) -> None:
        for database in list(reversed(self.created)):
            self.run("postgres", f'DROP DATABASE "{database}" WITH (FORCE);', "drop-" + database)
            self.created.remove(database)

    def execute(self) -> None:
        try:
            template = self.baseline()
            self.catalog_challenges(template)
            self.success_and_resume(template)
            self.success_and_resume(template, owner=True)
            for boundary, suffix in (
                ("-- CI_ADOPTION_BEFORE_HISTORY_BOUNDARY", "before_history"),
                ("-- CI_ADOPTION_AFTER_HISTORY_BOUNDARY", "after_history"),
            ):
                self.injected_failure(template, "sql_error_" + suffix, boundary, crash=False)
                self.injected_failure(template, "backend_kill_" + suffix, boundary, crash=True)
            self.concurrent_resume(template)
            self.history_rejection(template)
            self.history_rejection(template, marker=True)
            self.six_column_history_rejections(template)
            self.raw_collision(template)
            self.resume_metadata_rejection(template)
            self.full_history_resume(template)
            (self.evidence / "summary.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "scope": installer.PURPOSE,
                        "checks": self.checks,
                        "count": len(self.checks),
                        "source_commit": self.bind(template)["source_commit"],
                        "migration_inventory": installer.inventory(MIGRATIONS),
                        "qualified_hosted_application": "NOT_RUN",
                        "independent_application_plan_approval": "REQUIRED",
                        "prod_history_equivalence": "NOT_PROVEN",
                    },
                    indent=2,
                )
                + "\n"
            )
        finally:
            self.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    with contextlib.ExitStack():
        Rehearsal(args.evidence_dir).execute()


if __name__ == "__main__":
    main()
