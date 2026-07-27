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
    "intake_deep_links",
)

# M18-P05 opened exactly one path from the intake model into the catalogue:
# ``intake_sessions.listing_id``, written only by the vendor's explicit,
# ownership-checked submission. Every other intake table must still have no
# route into vendor_listings at all.
LISTING_LINK_TABLE = "intake_sessions"


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
    """Under the corrected D35, only M18-P05's handoff may reach the listing flow.

    A foreign key from any intake table to vendor_listings would mean the model
    itself had grown a path into the catalogue. ``intake_sessions.listing_id`` is
    the single, deliberate exception added by M18-P05 (asserted separately below,
    including that it is nullable and does not cascade); every other table must
    still have no route there.
    """
    tables = tuple(t for t in INTAKE_TABLES if t != LISTING_LINK_TABLE)
    quoted = ",".join(f"'{t}'" for t in tables)
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


def test_session_listing_link_is_nullable_and_does_not_cascade(db: PgConn) -> None:
    """M18-P05's one link into the catalogue, pinned to its intended shape.

    ``on delete set null`` (not cascade) is the point: removing a listing must
    never delete the intake session that records how it came to exist. Nullable
    is the other half — a session with no listing yet is the normal state.
    """
    result = db.run(
        """
        SELECT rc.delete_rule || '|' || c.is_nullable
        FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_name = tc.constraint_name
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
        JOIN information_schema.columns c
          ON c.table_schema = tc.table_schema
         AND c.table_name = tc.table_name
         AND c.column_name = kcu.column_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = 'intake_sessions'
          AND kcu.column_name = 'listing_id'
        """
    )
    assert result.ok, result.error
    assert result.rows == ["SET NULL|YES"], result.rows


def test_deep_links_store_no_plaintext_token(db: PgConn) -> None:
    """Only a hash column exists — a database read cannot rebuild a usable link."""
    result = db.run(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'intake_deep_links'
        ORDER BY column_name
        """
    )
    assert result.ok, result.error
    assert "token_hash" in result.rows
    assert "token" not in result.rows


def test_deep_link_hash_is_unique(db: PgConn) -> None:
    """Single-use enforcement leans on this: one row per token, ever."""
    result = db.run(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'intake_deep_links'
          AND indexdef ILIKE '%unique%'
          AND indexdef ILIKE '%token_hash%'
        """
    )
    assert result.ok, result.error
    assert result.rows, "expected a unique index on intake_deep_links.token_hash"
