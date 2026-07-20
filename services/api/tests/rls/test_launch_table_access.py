"""Access / cross-tenant proofs for D32 FORCE tables + registry additions.

Matrix EXPECTATIONS cover grant-level probes (DEFAULT VALUES / WHERE false).
These tests seed real rows and assert tenant/owner scoping and that the
trusted (migration/owner) path can still write product_relations.
"""

from __future__ import annotations

from typing import Any

from tests.rls.conftest import PgConn, RoleSession
from tests.rls.test_matrix import _is_permission_denied

SERVICE_REVIEW_ID = "c0ffee00-0000-4000-8000-0000000000a1"
TTI_ALLOC = 3


def test_anon_denied_service_reviews_without_grant(as_anon: RoleSession) -> None:
    result = as_anon.execute("SELECT 1 FROM public.service_reviews LIMIT 1")
    assert _is_permission_denied(result)


def test_anon_can_read_event_categories(as_anon: RoleSession) -> None:
    result = as_anon.execute("SELECT count(*)::int FROM public.event_categories")
    assert result.ok, result.error
    assert int(result.rows[0]) >= 1


def test_authenticated_cannot_write_event_categories(as_customer: RoleSession) -> None:
    result = as_customer.execute(
        "INSERT INTO public.event_categories (slug, label_key, sort) "
        "VALUES ('rls-probe-cat', 'rls.probe', 999)"
    )
    assert _is_permission_denied(result)


def test_admin_jwt_cannot_write_event_categories_without_grant(
    as_admin: RoleSession,
) -> None:
    """Admin RLS policy exists, but INSERT grant is service_role-only."""
    result = as_admin.execute(
        "INSERT INTO public.event_categories (slug, label_key, sort) "
        "VALUES ('rls-probe-admin', 'rls.probe', 998)"
    )
    assert _is_permission_denied(result)


def test_product_relations_clients_denied_and_owner_path_works(
    db: PgConn,
    as_anon: RoleSession,
    as_customer: RoleSession,
    as_admin: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    product_a = fixture_ids["products"]["phone"]
    product_b = fixture_ids["products"]["chitenge"]

    # Trusted path: connecting role (migration owner) can upsert.
    seed = db.run(
        f"""
BEGIN;
DELETE FROM public.product_relations
 WHERE product_id = '{product_a}' AND related_product_id = '{product_b}';
INSERT INTO public.product_relations (product_id, related_product_id, position)
VALUES ('{product_a}', '{product_b}', 0);
COMMIT;
"""
    )
    assert seed.ok, seed.error

    try:
        for session in (as_anon, as_customer, as_admin):
            denied = session.execute(
                f"SELECT count(*)::int FROM public.product_relations "
                f"WHERE product_id = '{product_a}'"
            )
            assert _is_permission_denied(denied), session.persona

            write = session.execute(
                f"INSERT INTO public.product_relations "
                f"(product_id, related_product_id, position) "
                f"VALUES ('{product_b}', '{product_a}', 1)"
            )
            assert _is_permission_denied(write), session.persona

        owned = db.run(
            f"SELECT count(*)::int FROM public.product_relations "
            f"WHERE product_id = '{product_a}' AND related_product_id = '{product_b}'"
        )
        assert owned.ok and owned.rows[0] == "1"
    finally:
        db.run(
            f"BEGIN; DELETE FROM public.product_relations "
            f"WHERE product_id IN ('{product_a}','{product_b}'); COMMIT;"
        )


def test_cross_organiser_cannot_mutate_ticket_type_instance(
    db: PgConn,
    as_vendor: RoleSession,
    as_other_vendor: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    """Demo festival is owned by shop_b (OTHER_VENDOR); shop_a must not update it."""
    tt_id = fixture_ids["ticket_types"]["ga"]
    instance_id = fixture_ids["event_instances"]["festival_night"]

    seed = db.run(
        f"""
BEGIN;
INSERT INTO public.ticket_type_instances (ticket_type_id, instance_id, allocation)
VALUES ('{tt_id}', '{instance_id}', {TTI_ALLOC})
ON CONFLICT (ticket_type_id, instance_id) DO UPDATE
  SET allocation = EXCLUDED.allocation;
COMMIT;
"""
    )
    assert seed.ok, seed.error

    try:
        own = as_other_vendor.execute(
            f"UPDATE public.ticket_type_instances SET allocation = {TTI_ALLOC + 1} "
            f"WHERE ticket_type_id = '{tt_id}' AND instance_id = '{instance_id}'"
        )
        assert own.ok, own.error

        rival = as_vendor.execute(
            f"UPDATE public.ticket_type_instances SET allocation = 99 "
            f"WHERE ticket_type_id = '{tt_id}' AND instance_id = '{instance_id}'"
        )
        assert rival.ok, rival.error

        check = db.run(
            f"SELECT allocation::int FROM public.ticket_type_instances "
            f"WHERE ticket_type_id = '{tt_id}' AND instance_id = '{instance_id}'"
        )
        # Rival UPDATE is RLS-filtered (0 rows); owner value unchanged.
        assert check.ok and check.rows[0] == str(TTI_ALLOC + 1)
    finally:
        db.run(
            f"BEGIN; DELETE FROM public.ticket_type_instances "
            f"WHERE ticket_type_id = '{tt_id}' AND instance_id = '{instance_id}'; "
            f"COMMIT;"
        )


def test_cross_organiser_cannot_mutate_ticket_price_tier(
    db: PgConn,
    as_vendor: RoleSession,
    as_other_vendor: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    tt_id = fixture_ids["ticket_types"]["ga"]
    seed = db.run(
        f"""
BEGIN;
DELETE FROM public.ticket_type_price_tiers WHERE ticket_type_id = '{tt_id}';
INSERT INTO public.ticket_type_price_tiers (ticket_type_id, min_qty, price_ngwee)
VALUES ('{tt_id}', 2, 5000);
COMMIT;
"""
    )
    assert seed.ok, seed.error

    try:
        own = as_other_vendor.execute(
            f"UPDATE public.ticket_type_price_tiers SET price_ngwee = 6000 "
            f"WHERE ticket_type_id = '{tt_id}' AND min_qty = 2"
        )
        assert own.ok, own.error

        rival = as_vendor.execute(
            f"UPDATE public.ticket_type_price_tiers SET price_ngwee = 1 "
            f"WHERE ticket_type_id = '{tt_id}' AND min_qty = 2"
        )
        assert rival.ok, rival.error

        check = db.run(
            f"SELECT price_ngwee::int FROM public.ticket_type_price_tiers "
            f"WHERE ticket_type_id = '{tt_id}' AND min_qty = 2"
        )
        assert check.ok and check.rows[0] == "6000"
    finally:
        db.run(
            f"BEGIN; DELETE FROM public.ticket_type_price_tiers "
            f"WHERE ticket_type_id = '{tt_id}'; COMMIT;"
        )


def test_service_review_non_published_hidden_from_peers(
    db: PgConn,
    as_other_customer: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    """Public SELECT policy is status='published' only."""
    job_id = fixture_ids["jobs"]["open_job"]
    customer_a = fixture_ids["users"]["customer_a"]
    vendor_a = fixture_ids["vendors"]["shop_a"]

    seed = db.run(
        f"""
BEGIN;
SET LOCAL session_replication_role = replica;
DELETE FROM public.service_reviews WHERE id = '{SERVICE_REVIEW_ID}';
INSERT INTO public.service_reviews (
  id, job_id, customer_id, provider_vendor_id, rating, body, status
) VALUES (
  '{SERVICE_REVIEW_ID}', '{job_id}', '{customer_a}', '{vendor_a}',
  5, 'flagged peer hidden', 'flagged'
);
COMMIT;
"""
    )
    assert seed.ok, seed.error

    try:
        peer = as_other_customer.execute(
            f"SELECT count(*)::int FROM public.service_reviews "
            f"WHERE id = '{SERVICE_REVIEW_ID}'"
        )
        assert peer.ok, peer.error
        assert peer.rows[0] == "0"
    finally:
        db.run(
            f"BEGIN; DELETE FROM public.service_reviews "
            f"WHERE id = '{SERVICE_REVIEW_ID}'; COMMIT;"
        )
