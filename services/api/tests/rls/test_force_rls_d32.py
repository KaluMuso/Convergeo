"""D32 / G0: every required table has RLS enabled AND forced.

Locked decision D32 requires FORCE ROW LEVEL SECURITY on
`ticket_type_instances`, `ticket_type_price_tiers`, and `product_relations`.
Gate G0's inventory also requires RLS (+ FORCE where decided) on the money /
identity tables listed below — table-owner sessions must not bypass policies.
"""

from __future__ import annotations

from tests.rls.conftest import PgConn

# D32 explicit targets (migration 0064).
D32_FORCE_TABLES: tuple[str, ...] = (
    "ticket_type_instances",
    "ticket_type_price_tiers",
    "product_relations",
)

# G0 inventory from docs/production-readiness/.../release-gates.md — every row
# must have relrowsecurity; the D32 subset must also have relforcerowsecurity.
G0_RLS_TABLES: tuple[str, ...] = (
    "orders",
    "payments",
    "ledger_transactions",
    "ledger_postings",
    "tickets",
    "ticket_type_instances",
    "ticket_type_price_tiers",
    "user_roles",
    "vendors",
    "vendor_listings",
    "kyc_records",
    "product_relations",
)

# Post-deploy verification (same shape as release-gates G0):
# SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
# FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
# WHERE n.nspname='public' AND c.relkind='r'
#   AND c.relname IN (
#     'ticket_type_instances','ticket_type_price_tiers','product_relations'
#   )
# ORDER BY 1;


def _flags(db: PgConn, tables: tuple[str, ...]) -> dict[str, tuple[bool, bool]]:
    quoted = ",".join(f"'{t}'" for t in tables)
    result = db.run(
        f"""
        SELECT c.relname || '|' || c.relrowsecurity || '|' || c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND c.relname IN ({quoted})
        ORDER BY 1
        """
    )
    assert result.ok, result.error
    out: dict[str, tuple[bool, bool]] = {}
    for row in result.rows:
        name, rls, force = row.split("|")
        out[name] = (_as_bool(rls), _as_bool(force))
    return out


def _as_bool(value: str) -> bool:
    # psql -At stringifies booleans as 't'/'f' or 'true'/'false' depending on
    # whether they were cast via || vs ::text.
    return value.lower() in {"t", "true", "1"}


def test_d32_force_rls_targets(db: PgConn) -> None:
    flags = _flags(db, D32_FORCE_TABLES)
    missing = sorted(set(D32_FORCE_TABLES) - set(flags))
    assert not missing, f"D32 tables absent from schema: {missing}"
    for table in D32_FORCE_TABLES:
        rls, force = flags[table]
        assert rls, f"{table}: relrowsecurity expected true"
        assert force, f"{table}: relforcerowsecurity expected true (D32 / 0064)"


def test_g0_inventory_rls_enabled(db: PgConn) -> None:
    flags = _flags(db, G0_RLS_TABLES)
    missing = sorted(set(G0_RLS_TABLES) - set(flags))
    assert not missing, f"G0 tables absent from schema: {missing}"
    for table in G0_RLS_TABLES:
        rls, _force = flags[table]
        assert rls, f"{table}: relrowsecurity expected true (G0)"


def test_g0_d32_subset_is_forced(db: PgConn) -> None:
    """Intersection of G0 inventory and D32 must be FORCE'd."""
    flags = _flags(db, D32_FORCE_TABLES)
    for table in D32_FORCE_TABLES:
        assert table in G0_RLS_TABLES
        assert flags[table] == (True, True), table
