"""Admin-controlled catalog taxonomy — RLS and invariants (20261127130000).

Live Postgres (``supabase db reset`` first), same harness as the other RLS suites. The
generic persona x verb grid for categories / event_categories / service_categories stays in
``test_matrix.py`` (select-only for every client persona); this file covers the *row* rules.
"""

from __future__ import annotations

from tests.rls.conftest import PgConn, RoleSession

TABLES = ("categories", "event_categories", "service_categories")


def _seed_service_nodes(db: PgConn) -> None:
    result = db.run(
        """
        BEGIN;
        INSERT INTO public.service_categories
          (slug, name, path, status, show_in_customer, show_in_vendor)
        VALUES
          ('tx-pub', 'Pub', 'tx-pub', 'published', true, true),
          ('tx-draft', 'Draft', 'tx-draft', 'draft', true, true),
          ('tx-blocked', 'Blocked', 'tx-blocked', 'blocked', true, true),
          ('tx-hidden', 'Hidden', 'tx-hidden', 'published', false, false),
          ('tx-vendor-only', 'Vendor', 'tx-vendor-only', 'published', false, true);
        COMMIT;
        """
    )
    assert result.ok, result.error


def _cleanup(db: PgConn) -> None:
    db.run("BEGIN; DELETE FROM public.service_categories WHERE slug LIKE 'tx-%'; COMMIT;")


def test_taxonomy_tables_force_rls(db: PgConn) -> None:
    for table in TABLES:
        result = db.run(
            f"SELECT relforcerowsecurity FROM pg_class WHERE oid = 'public.{table}'::regclass"
        )
        assert result.ok and result.rows == ["t"], table


def test_anon_reads_only_published_visible_nodes(db: PgConn, as_anon: RoleSession) -> None:
    _seed_service_nodes(db)
    try:
        result = as_anon.execute(
            "SELECT string_agg(slug, ',' ORDER BY slug) FROM public.service_categories "
            "WHERE slug LIKE 'tx-%'"
        )
        assert result.ok, result.error
        # One aggregated row: the harness keeps only the last row of a BEGIN-wrapped script.
        assert result.rows == ["tx-pub,tx-vendor-only"]
    finally:
        _cleanup(db)


def test_client_roles_cannot_write_taxonomy(
    db: PgConn, as_anon: RoleSession, as_admin: RoleSession
) -> None:
    for session in (as_anon, as_admin):
        for table, columns, values in (
            ("service_categories", "(slug, name, path)", "('tx-x', 'X', 'tx-x')"),
            ("event_categories", "(slug, label_key)", "('tx-x', 'k')"),
        ):
            result = session.execute(f"INSERT INTO public.{table} {columns} VALUES {values}")
            assert not result.ok, table


def test_existing_service_verticals_seeded_and_new_ones_start_draft(db: PgConn) -> None:
    result = db.run(
        "SELECT slug || ':' || status FROM public.service_categories "
        "WHERE slug IN ('beauty','tailoring','logistics-delivery','packaging-supplies') "
        "ORDER BY slug"
    )
    assert result.ok, result.error
    assert result.rows == [
        "beauty:published",
        "logistics-delivery:draft",
        "packaging-supplies:draft",
        "tailoring:published",
    ]


def test_existing_categories_default_to_published_product_visible(db: PgConn) -> None:
    result = db.run(
        "SELECT count(*) FROM public.categories WHERE umbrella <> 'product' "
        "OR status <> 'published' OR NOT show_in_customer OR NOT show_in_vendor"
    )
    assert result.ok, result.error
    assert result.rows == ["0"]


def test_child_category_must_share_parent_umbrella(db: PgConn) -> None:
    result = db.run(
        """
        BEGIN;
        WITH parent AS (
          INSERT INTO public.categories (name, slug, path, commission_key, umbrella)
          VALUES ('TX parent', 'tx-parent', 'tx-parent', 'default', 'wholesale')
          RETURNING id
        )
        INSERT INTO public.categories (name, slug, path, commission_key, umbrella, parent_id)
        SELECT 'TX child', 'tx-child', 'tx-parent/tx-child', 'default', 'product', id FROM parent;
        COMMIT;
        """
    )
    assert not result.ok
    db.run("BEGIN; DELETE FROM public.categories WHERE slug LIKE 'tx-%'; COMMIT;")
