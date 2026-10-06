"""SYNTHETIC ONLY controls for the disposable six-column history fixture."""

from __future__ import annotations

import subprocess
import unittest
from typing import Any
from unittest.mock import patch

import apply_service_adoption_disposable as installer

BASELINE = "b6947e0014d4e8171ff0bcf699f7146760dd656c"
MIGRATIONS = installer.ROOT / "supabase/migrations"


class SyntheticHistoryControls(unittest.TestCase):
    rows: list[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = installer.history_rows(MIGRATIONS)

    def test_unchanged_114_file_source_baseline(self) -> None:
        names = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", BASELINE, "supabase/migrations"],
            cwd=installer.ROOT, text=True,
        ).splitlines()
        names = [name for name in names if name.endswith(".sql")]
        self.assertEqual(len(names), 114)
        current = ["supabase/migrations/" + path.name for path in sorted(MIGRATIONS.glob("*.sql"))]
        self.assertEqual(current[:114], names)
        for name in names:
            old = subprocess.check_output(
                ["git", "rev-parse", BASELINE + ":" + name],
                cwd=installer.ROOT, text=True,
            ).strip()
            now = subprocess.check_output(
                ["git", "hash-object", name], cwd=installer.ROOT, text=True,
            ).strip()
            self.assertEqual(now, old, name)

    def test_six_column_shape_and_provisional_order(self) -> None:
        rows = self.rows
        self.assertEqual(len(rows), 138)
        self.assertEqual(rows[0]["statements"], None)
        self.assertEqual(rows[1]["statements"], [])
        self.assertEqual(rows[2]["statements_bounds"], "[0:0]")
        self.assertEqual(rows[2]["rollback_bounds"], "[-2:-2]")
        self.assertIsNone(rows[0]["rollback"])
        self.assertEqual(rows[3]["rollback"], [])
        keys = [row["idempotency_key"] for row in rows if row["idempotency_key"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(rows[114]["version"], "20260921155234")
        self.assertEqual(rows[130]["version"], installer.VERSION)
        self.assertEqual(len(rows[131:]), 7)

    def test_insert_preserves_null_empty_bounds_and_unique_metadata(self) -> None:
        for row in self.rows[:114]:
            sql = installer.history_insert(row)
            self.assertIn("(version,statements,name,created_by,idempotency_key,rollback)", sql)
            self.assertIn("::text[]", sql)
        self.assertIn("NULL::text[]", installer.history_insert(self.rows[0]))
        self.assertIn("ARRAY[]::text[]", installer.history_insert(self.rows[1]))
        self.assertIn("[0:0]=", installer.history_insert(self.rows[2]))
        self.assertIn("[-2:-2]=", installer.history_insert(self.rows[2]))

    def test_render_checks_exact_prefix_and_atomic_insert(self) -> None:
        fixture = {"container_id": "a" * 64, "image_id": "b" * 64,
                   "server_address": "127.0.0.1"}
        with patch.object(installer, "fixture_binding", return_value=fixture):
            bound = installer.plan(
                "ci_adoption_123456789abc_fixture",
                installer.MARKER_PREFIX + "ci_adoption_123456789abc_fixture", MIGRATIONS,
            )
            sql = installer.render(bound, MIGRATIONS)
        self.assertEqual(bound["ledger_before_count"], 130)
        self.assertIn("actual IS DISTINCT FROM prefix", sql)
        self.assertIn("array_dims(m.statements)", sql)
        self.assertIn("array_dims(m.rollback)", sql)
        self.assertIn("attname='idempotency_key'", sql)
        self.assertIn("contype='u'", sql)
        self.assertIn("-- CI_ADOPTION_BEFORE_HISTORY_BOUNDARY", sql)
        self.assertIn("-- CI_ADOPTION_AFTER_HISTORY_BOUNDARY", sql)
        self.assertIn("--single-transaction", installer.connection_arguments(bound))


if __name__ == "__main__":
    unittest.main()
