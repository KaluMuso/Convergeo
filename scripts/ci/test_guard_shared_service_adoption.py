"""Shared adoption prerequisite controls; no shared connections or writes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import apply_service_adoption as adoption
import guard_shared_service_adoption as guard

SOURCE = "a" * 40
PROJECT = "iyasmrmbcrvlfxpzescb"


def fixtures() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    row: dict[str, Any] = {
        "version": guard.VERSION,
        "name": guard.NAME,
        "statements": [
            (adoption.ROOT / "supabase/migrations" / adoption.ADOPTION).read_text()
        ],
    }
    evidence: dict[str, Any] = {
        "purpose": "SHARED_ADOPTION_APPLICATION_REVIEW",
        "source_sha": SOURCE,
        "project_ref": PROJECT,
        "adoption_sha256": adoption.ADOPTION_SHA256,
        "canonical_row_sha256": guard.row_digest(row),
        "review_verdict": "APPROVED_FOR_TARGET_APPLICATION",
        "reviewer": "independent-test-reviewer",
        "review_record_sha256": "b" * 64,
        "review_record_url": "https://example.invalid/review",
        "application_record_url": "https://example.invalid/application",
    }
    return [row], evidence


def catalog_fixture() -> dict[str, Any]:
    source = (adoption.ROOT / "supabase/migrations" / adoption.AUTHORITY).read_text()
    routine = source.split(
        "create function public.create_service_payment_obligations(", 1
    )[1]
    return {
        "schema": "public",
        "name": "create_service_payment_obligations",
        "arguments": "uuid, uuid, uuid, bigint, bigint",
        "result": "void",
        "language": "plpgsql",
        "prokind": "f",
        "prosecdef": True,
        "proisstrict": False,
        "proleakproof": False,
        "provolatile": "v",
        "proparallel": "u",
        "proretset": False,
        "pronargdefaults": 0,
        "proargnames": ["p_order_id", "p_job_id", "p_customer_id", "p_total", "p_deposit"],
        "proconfig": ['search_path=""'],
        "prosrc": routine.split("as $$", 1)[1].split("$$;", 1)[0],
        "acl": [
            {
                "owner": True,
                "grantee": "fixture_owner",
                "privilege": "EXECUTE",
                "grantable": False,
            },
            {
                "owner": False,
                "grantee": "service_role",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ],
    }


class SharedAdoptionGuard(unittest.TestCase):
    def verify(self, rows: object, evidence: object) -> None:
        guard.validate(
            rows,
            evidence,
            catalog=catalog_fixture(),
            source_sha=SOURCE,
            project_ref=PROJECT,
            migrations=adoption.ROOT / "supabase/migrations",
        )

    def test_exact_history_and_bound_supplied_review_pass(self) -> None:
        self.verify(*fixtures())

    def test_canonical_ledger_cannot_hide_missing_or_drifted_catalog(self) -> None:
        rows, evidence = fixtures()
        canonical = catalog_fixture()
        mutations: list[Any] = [
            None,
            [],
            {},
            {**canonical, "prosrc": "begin return; end;"},
        ]
        # Each expected catalog fact is required, independently of ledger text.
        mutations.extend(
            {k: v for k, v in canonical.items() if k != key} for key in canonical
        )
        for key, value in {
            "schema": "other",
            "name": "alias",
            "arguments": "uuid",
            "result": "boolean",
            "language": "sql",
            "prokind": "p",
            "prosecdef": False,
            "proisstrict": True,
            "proleakproof": True,
            "provolatile": "s",
            "proparallel": "s",
            "proretset": True,
            "pronargdefaults": 1,
            "proconfig": ["search_path=public"],
        }.items():
            mutations.append({**canonical, key: value})
        for acl in (
            None,
            [],
            canonical["acl"][:1],
            [
                *canonical["acl"],
                {
                    "owner": False,
                    "grantee": "PUBLIC",
                    "privilege": "EXECUTE",
                    "grantable": False,
                },
            ],
            [
                *canonical["acl"],
                {
                    "owner": False,
                    "grantee": "authenticated",
                    "privilege": "EXECUTE",
                    "grantable": False,
                },
            ],
            [{**canonical["acl"][1], "grantable": True}],
        ):
            mutations.append({**canonical, "acl": acl})
        for catalog in mutations:
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                guard.validate(
                    rows,
                    evidence,
                    catalog=catalog,
                    source_sha=SOURCE,
                    project_ref=PROJECT,
                    migrations=adoption.ROOT / "supabase/migrations",
                )

    def test_canonical_ledger_cannot_hide_argument_name_drift(self) -> None:
        rows, evidence = fixtures()
        canonical = catalog_fixture()
        for names in (
            ["p_job_id", "p_order_id", "p_customer_id", "p_total", "p_deposit"],
            ["renamed_order_id", "p_job_id", "p_customer_id", "p_total", "p_deposit"],
            None,
        ):
            with self.subTest(names=names), self.assertRaises(ValueError):
                guard.validate(
                    rows, evidence, catalog={**canonical, "proargnames": names},
                    source_sha=SOURCE, project_ref=PROJECT,
                    migrations=adoption.ROOT / "supabase/migrations",
                )

    def test_catalog_query_failure_or_absence_blocks_success(self) -> None:
        rows, evidence = fixtures()
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_DB_URL": f"postgresql://postgres@db.{PROJECT}.supabase.co/postgres",
                    "SCHEMA_TARGET_PROJECT_REF": PROJECT,
                    "EXPECTED_SOURCE_SHA": SOURCE,
                    "SERVICE_ADOPTION_REVIEW_EVIDENCE_JSON": json.dumps(evidence),
                },
            ),
            patch.object(subprocess, "check_output", return_value=SOURCE),
            patch.object(subprocess, "run") as run,
            patch("builtins.print") as output,
        ):
            for response in (
                {"history": rows, "authority": None},
                {"history": rows},
                rows,
            ):
                run.return_value.returncode = 0
                run.return_value.stdout = json.dumps(response)
                with self.assertRaises(ValueError):
                    guard.main()
            run.return_value.returncode = 1
            with self.assertRaisesRegex(ValueError, "query failed"):
                guard.main()
            output.assert_not_called()

    def test_absent_null_drifted_or_aliased_history_refused(self) -> None:
        rows, evidence = fixtures()
        for mutation in (
            [],
            [{**rows[0], "statements": None}],
            [{**rows[0], "statements": ["do $$ begin null; end $$;"]}],
            [{**rows[0], "name": "alias"}],
            [{**rows[0], "version": "120003"}],
        ):
            with self.subTest(rows=mutation), self.assertRaises(ValueError):
                self.verify(mutation, evidence)

    def test_missing_or_misbound_independent_review_refused(self) -> None:
        rows, evidence = fixtures()
        for key in evidence:
            mutated = {k: v for k, v in evidence.items() if k != key}
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.verify(rows, mutated)
        for key in (
            "source_sha",
            "project_ref",
            "canonical_row_sha256",
            "adoption_sha256",
        ):
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.verify(rows, {**evidence, key: "wrong"})

    def test_query_runs_read_only_on_the_exact_bound_dsn(self) -> None:
        rows, evidence = fixtures()
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_DB_URL": "postgresql://postgres:fixture-secret@db.iyasmrmbcrvlfxpzescb.supabase.co:5432/postgres",
                    "PGHOST": "wrong-host",
                    "PGPORT": "6543",
                    "PGHOSTADDR": "127.0.0.1",
                    "PGSERVICE": "unreviewed",
                    "PGSERVICEFILE": "/tmp/unreviewed",
                    "PGOPTIONS": "-crole=anon",
                    "EXPECTED_SOURCE_SHA": SOURCE,
                    "SCHEMA_TARGET_PROJECT_REF": PROJECT,
                    "SERVICE_ADOPTION_REVIEW_EVIDENCE_JSON": json.dumps(evidence),
                },
            ),
            patch.object(subprocess, "check_output", return_value=SOURCE + "\n"),
            patch.object(subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(
                {"history": rows, "authority": catalog_fixture()}
            )
            guard.main()
            self.assertEqual(
                run.call_args.args[0][-2:],
                [
                    "--dbname",
                    "postgresql://postgres:fixture-secret@db.iyasmrmbcrvlfxpzescb.supabase.co:5432/postgres",
                ],
            )
            for key in (
                "PGHOST",
                "PGHOSTADDR",
                "PGPORT",
                "PGSERVICE",
                "PGSERVICEFILE",
                "PGOPTIONS",
            ):
                self.assertNotIn(key, run.call_args.kwargs["env"])
            self.assertIn("BEGIN READ ONLY;", run.call_args.kwargs["input"])
            self.assertNotIn("INSERT", run.call_args.kwargs["input"])
            self.assertNotIn("UPDATE", run.call_args.kwargs["input"])
            for required in (
                "pg_catalog.pg_proc",
                "p.prosrc",
                "p.proargnames",
                "p.proconfig",
                "pg_catalog.aclexplode",
                "pg_catalog.acldefault",
                "pg_catalog.to_regprocedure",
            ):
                self.assertIn(required, run.call_args.kwargs["input"])
            self.assertNotIn("DO $", run.call_args.kwargs["input"])
            self.assertNotIn("CREATE", run.call_args.kwargs["input"])

    def test_source_identity_mismatch_refuses_before_database_query(self) -> None:
        _, evidence = fixtures()
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_DB_URL": f"postgresql://postgres@db.{PROJECT}.supabase.co/postgres",
                    "SCHEMA_TARGET_PROJECT_REF": PROJECT,
                    "EXPECTED_SOURCE_SHA": "c" * 40,
                    "SERVICE_ADOPTION_REVIEW_EVIDENCE_JSON": json.dumps(evidence),
                },
            ),
            patch.object(subprocess, "check_output", return_value=SOURCE + "\n"),
            patch.object(subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(ValueError, "actual checkout"):
                guard.main()
            run.assert_not_called()

    def test_workflow_clears_routing_for_guard_and_push(self) -> None:
        import shlex

        text = (adoption.ROOT / ".github/workflows/deploy-staging.yml").read_text()
        start = text.index(
            "          unset PGHOST PGHOSTADDR PGPORT PGSERVICE PGSERVICEFILE PGOPTIONS"
        )
        end = text.index("\n\n      - name: Reconcile repository", start)
        snippet = "\n".join(line[10:] for line in text[start:end].splitlines())
        keys = [
            "PGHOST",
            "PGHOSTADDR",
            "PGPORT",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGOPTIONS",
        ]
        check = "import os; assert not set(" + repr(keys) + ") & os.environ.keys()"
        snippet = snippet.replace(
            "python3 scripts/ci/guard_shared_service_adoption.py",
            shlex.quote(sys.executable) + " -c " + shlex.quote(check),
        )
        with tempfile.TemporaryDirectory() as directory:
            fake_cli = Path(directory) / "supabase"
            fake_cli.write_text("#!" + sys.executable + "\n" + check + "\n")
            fake_cli.chmod(0o755)
            env = dict(os.environ, **{key: "unreviewed-routing" for key in keys})
            env.update(
                PATH=directory + os.pathsep + env["PATH"],
                STAGING_SUPABASE_PROJECT_ID=PROJECT,
                SUPABASE_DB_URL="fixture-dsn",
            )
            result = subprocess.run(
                ["bash", "-euc", snippet], env=env, text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_target_dsn_indirection_and_production_are_refused(self) -> None:
        guard.validate_dsn_binding(
            f"postgresql://postgres@db.{PROJECT}.supabase.co/postgres", PROJECT
        )
        guard.validate_dsn_binding(
            f"postgresql://postgres.{PROJECT}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
            PROJECT,
        )
        for dsn in (
            "postgresql://postgres@localhost/postgres",
            "postgresql://postgres@db.dpadrlxukcjbewpqympu.supabase.co/postgres",
            f"postgresql://postgres.{PROJECT}@custom.example.com/postgres",
            f"postgresql://postgres@db.{PROJECT}.supabase.co/postgres?hostaddr=127.0.0.1",
            f"postgresql://postgres@db.{PROJECT}.supabase.co/postgres?service=other",
            f"postgresql://postgres@db.{PROJECT}.supabase.co/postgres?options=-crole%3Danon",
        ):
            with self.subTest(dsn=dsn), self.assertRaises(ValueError):
                guard.validate_dsn_binding(dsn, PROJECT)

    def test_staging_guard_precedes_every_push_and_same_dsn_is_used(self) -> None:
        text = (adoption.ROOT / ".github/workflows/deploy-staging.yml").read_text()
        self.assertEqual(text.count("supabase db push --"), 1)
        self.assertLess(
            text.index("python3 scripts/ci/guard_shared_service_adoption.py"),
            text.index("supabase db push --"),
        )
        self.assertIn(
            'supabase db push --db-url "${SUPABASE_DB_URL}" --include-all', text
        )
        production = (
            adoption.ROOT / ".github/workflows/deploy-production.yml"
        ).read_text()
        self.assertNotIn("supabase db push", production)
        self.assertNotIn("apply_service_adoption_disposable", text)


if __name__ == "__main__":
    unittest.main()
