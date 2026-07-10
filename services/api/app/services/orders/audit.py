"""Transaction-local audit context for order status changes."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

_DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

ORDER_ACTOR_GUC = "app.order_actor"
ORDER_NOTE_GUC = "app.order_note"


@dataclass(frozen=True, slots=True)
class SqlResult:
    ok: bool
    rows: list[str]
    error: str | None = None


def resolve_db_url() -> str:
    return os.environ.get("SUPABASE_DB_URL", _DEFAULT_DB_URL)


def sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def run_sql_script(script: str) -> SqlResult:
    proc = subprocess.run(
        ["psql", resolve_db_url(), "-v", "ON_ERROR_STOP=1", "-At"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return SqlResult(ok=False, rows=[], error=proc.stderr.strip())
    rows = [line for line in proc.stdout.splitlines() if line]
    noise = {"BEGIN", "COMMIT", "ROLLBACK", "DO", "SET"}
    data = [
        row
        for row in rows
        if row not in noise and not re.match(r"^(?:INSERT|UPDATE|DELETE|SELECT) \d+$", row)
    ]
    return SqlResult(ok=True, rows=data)


def set_order_audit_context(*, actor_id: str, note: str) -> None:
    """Prime audit trigger GUCs for the current transaction."""
    script = f"""
SELECT set_config('{ORDER_ACTOR_GUC}', {sql_literal(actor_id)}, true);
SELECT set_config('{ORDER_NOTE_GUC}', {sql_literal(note)}, true);
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"set_order_audit_context failed: {result.error}")
