"""M18-P01 — every WAHA intake table has RLS enabled AND forced (D35).

FORCE matters here specifically because the ingestion path runs as the service
role. Without FORCE, a table-owner session would bypass the per-vendor policies
entirely, and a bug in the API layer would become a cross-vendor data leak
rather than a contained error.

Also asserts the two structural invariants the ingestion code relies on:
the append-only shape of ``intake_events`` and the one-active-binding-per-number
unique index that makes "known verified sender" unambiguous.
"""

from __future__ import annotations

from tests.rls.conftest import PgConn

INTAKE_TABLES: tuple[str, ...] = (
    "intake_vendor_bindings",
    "intake_sessions",
    "intake_messages",
    "intake_media",
    "intake_draft_fields",
    "intake_field_provenance",
    "intake_events",
)


def _as_bool(value: str) -> bool:
    return value.lower() in {"t", "true", "1"}


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


def test_every_intake_table_forces_rls(db: PgConn) -> None:
    flags = _flags(db, INTAKE_TABLES)
    missing = sorted(set(INTAKE_TABLES) - set(flags))
    assert not missing, f"Intake tables absent from schema: {missing}"
    for table in INTAKE_TABLES:
        rls, force = flags[table]
        assert rls, f"{table}: relrowsecurity expected true"
        assert force, f"{table}: relforcerowsecurity expected true (D35)"


def test_no_client_role_holds_intake_privileges(db: PgConn) -> None:
    """Intake tables are service_role only — anon/authenticated get nothing.

    This is the outer lock: a client cannot reach these tables even before RLS
    is consulted.
    """
    quoted = ",".join(f"'{t}'" for t in INTAKE_TABLES)
    result = db.run(
        f"""
        SELECT table_name || '|' || grantee || '|' || privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema = 'public'
          AND table_name IN ({quoted})
          AND grantee IN ('anon', 'authenticated')
        ORDER BY 1
        """
    )
    assert result.ok, result.error
    assert result.rows == [], f"unexpected client grants on intake tables: {result.rows}"


def test_intake_events_is_append_only(db: PgConn) -> None:
    """No UPDATE or DELETE privilege exists for any role, including service_role."""
    result = db.run(
        """
        SELECT grantee || '|' || privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema = 'public'
          AND table_name = 'intake_events'
          AND privilege_type IN ('UPDATE', 'DELETE')
        ORDER BY 1
        """
    )
    assert result.ok, result.error
    assert result.rows == [], f"intake_events must be append-only, found: {result.rows}"


def test_one_active_binding_per_msisdn(db: PgConn) -> None:
    """The unique partial index is what makes an ambiguous sender impossible."""
    result = db.run(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'intake_vendor_bindings'
          AND indexname = 'intake_vendor_bindings_active_msisdn_uniq'
        """
    )
    assert result.ok, result.error
    assert result.rows, "expected the active-binding unique index to exist"
    definition = result.rows[0].lower()
    assert "unique" in definition
    assert "msisdn" in definition
    assert "opted_out_at is null" in definition


def test_intake_tables_do_not_reference_vendor_listings(db: PgConn) -> None:
    """Under the corrected D35, only M18-P05 may reach the listing flow.

    A foreign key from any intake table to vendor_listings would mean the model
    itself had grown a path into the catalogue.
    """
    quoted = ",".join(f"'{t}'" for t in INTAKE_TABLES)
    result = db.run(
        f"""
        SELECT tc.table_name || '->' || ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name IN ({quoted})
          AND ccu.table_name = 'vendor_listings'
        """
    )
    assert result.ok, result.error
    assert result.rows == [], f"intake model must not reference vendor_listings: {result.rows}"
