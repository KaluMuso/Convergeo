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


class SharedAdoptionGuard(unittest.TestCase):
    def verify(self, rows: object, evidence: object) -> None:
        guard.validate(
            rows,
            evidence,
            source_sha=SOURCE,
            project_ref=PROJECT,
            migrations=adoption.ROOT / "supabase/migrations",
        )

    def test_exact_history_and_bound_supplied_review_pass(self) -> None:
        self.verify(*fixtures())

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
            run.return_value.stdout = json.dumps(rows)
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
