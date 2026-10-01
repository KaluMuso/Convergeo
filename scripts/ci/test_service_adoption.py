"""Source/transaction controls; real upgrade evidence is recorded separately."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apply_service_adoption as adoption


class AdoptionControls(unittest.TestCase):
    def test_guard_precedes_adoption_and_restores_authority(self) -> None:
        sql = adoption.migration_sql(adoption.ROOT / "supabase/migrations")
        marker = "declare o public.orders%rowtype; spine record"
        self.assertLess(sql.index("checkout_shared_by_orders"), sql.index(marker))
        self.assertEqual(sql.count(
            "create or replace function public.create_service_payment_obligations"
        ), 2)
        self.assertGreater(sql.rindex("create or replace function"), sql.index(marker))
        self.assertNotIn("exception when unique_violation", sql.lower())
        self.assertNotIn("delete from", sql.lower())

    def test_unknown_immutable_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in (adoption.AUTHORITY, adoption.ADOPTION):
                content = (adoption.ROOT / "supabase/migrations" / name).read_bytes()
                (target / name).write_bytes(content)
            (target / adoption.ADOPTION).write_text("do $$ begin null; end $$;")
            with self.assertRaisesRegex(ValueError, "Immutable"):
                adoption.migration_sql(target)

    def test_execution_is_atomic_and_preserves_psql_failure(self) -> None:
        with (
            patch("sys.argv", ["apply_service_adoption"]),
            patch.object(subprocess, "run") as run,
        ):
            run.return_value.returncode = 3
            with self.assertRaises(SystemExit) as error:
                adoption.main()
            self.assertEqual(error.exception.code, 3)
            arguments = run.call_args.args[0]
            self.assertIn("--single-transaction", arguments)
            self.assertIn("ON_ERROR_STOP=1", arguments)
            self.assertTrue(run.call_args.kwargs["input"].startswith("SET LOCAL lock_timeout"))


if __name__ == "__main__":
    unittest.main()
