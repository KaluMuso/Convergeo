"""Transaction-local audit context for order status changes.

The SQL write path (``run_sql_script`` / ``SqlResult`` / ``resolve_db_url``) lives in
``app.services.db`` — the one authoritative native-psycopg adapter. It is re-exported
here so the long-standing ``from app.services.orders.audit import run_sql_script``
call sites (and their test monkeypatch seams) keep working unchanged.
"""

from __future__ import annotations

from app.services.db import SqlResult as SqlResult
from app.services.db import resolve_db_url as resolve_db_url
from app.services.db import run_sql_script as run_sql_script

ORDER_ACTOR_GUC = "app.order_actor"
ORDER_NOTE_GUC = "app.order_note"


def sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def set_order_audit_context(*, actor_id: str, note: str) -> None:
    """Prime audit trigger GUCs for the current transaction."""
    script = f"""
SELECT set_config('{ORDER_ACTOR_GUC}', {sql_literal(actor_id)}, true);
SELECT set_config('{ORDER_NOTE_GUC}', {sql_literal(note)}, true);
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"set_order_audit_context failed: {result.error}")
