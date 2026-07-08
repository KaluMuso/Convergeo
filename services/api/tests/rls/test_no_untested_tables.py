"""Fail CI when a migration adds a public table without matrix expectations."""

from __future__ import annotations

from tests.rls.conftest import PgConn
from tests.rls.test_matrix import EXPECTATIONS


def _tables_in_db(db: PgConn) -> set[str]:
    result = db.run(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    assert result.ok, result.error
    return set(result.rows)


def test_no_untested_tables(db: PgConn) -> None:
    live = _tables_in_db(db)
    documented = set(EXPECTATIONS.keys())
    missing = sorted(live - documented)
    assert not missing, f"Tables missing from EXPECTATIONS: {missing}"
