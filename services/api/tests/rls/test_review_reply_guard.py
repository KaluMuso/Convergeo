"""RLS/trigger test for the review vendor-reply column guard (migration 0060).

A vendor owns the row-level UPDATE policy on reviews of their own listings, but must
only be able to write vendor_reply / vendor_reply_at — never rating / body / status.
Admins and the service role keep full moderation control.

DB-backed (mirrors the RLS matrix harness); skips when Postgres is unavailable.
"""

from __future__ import annotations

from typing import Any

from tests.rls.conftest import PgConn, RoleSession

REVIEW_ID = "ba5eba11-0000-0000-0000-000000000001"


def _seed_review(db: PgConn, *, order_item_id: str) -> None:
    # Seeded as the connecting superuser: bypasses RLS + the verified-engagement
    # BEFORE INSERT trigger (which itself allows postgres/supabase_admin sessions).
    result = db.run(
        f"""
BEGIN;
DELETE FROM public.reviews WHERE order_item_id = '{order_item_id}';
DELETE FROM public.reviews WHERE id = '{REVIEW_ID}';
INSERT INTO public.reviews (id, order_item_id, rating, body, status)
VALUES ('{REVIEW_ID}', '{order_item_id}', 1, 'poor', 'published');
COMMIT;
"""
    )
    assert result.ok, f"seed failed: {result.error}"


def _cleanup(db: PgConn) -> None:
    db.run(f"BEGIN; DELETE FROM public.reviews WHERE id = '{REVIEW_ID}'; COMMIT;")


def _rating(db: PgConn) -> str | None:
    result = db.run(f"SELECT rating::text FROM public.reviews WHERE id = '{REVIEW_ID}'")
    return result.rows[0] if result.ok and result.rows else None


def test_vendor_cannot_rewrite_review_rating_or_status_but_may_reply(
    db: PgConn,
    as_vendor: RoleSession,
    as_admin: RoleSession,
    fixture_ids: dict[str, Any],
) -> None:
    order_item_id = fixture_ids["order_items"]["paid"]  # phone_a -> vendor_a (VENDOR persona)
    _seed_review(db, order_item_id=order_item_id)
    try:
        # Vendor rewriting the star rating is rejected by the 0060 column guard,
        # even though the row-level vendor-reply policy permits the row.
        rating_attempt = as_vendor.execute(
            f"UPDATE public.reviews SET rating = 5 WHERE id = '{REVIEW_ID}'"
        )
        assert not rating_attempt.ok
        assert "vendor_reply" in (rating_attempt.error or "")
        assert _rating(db) == "1"

        # Flipping status to hide the review is likewise rejected.
        status_attempt = as_vendor.execute(
            f"UPDATE public.reviews SET status = 'removed' WHERE id = '{REVIEW_ID}'"
        )
        assert not status_attempt.ok

        # The legitimate vendor reply succeeds.
        reply = as_vendor.execute(
            f"UPDATE public.reviews SET vendor_reply = 'Thanks for the feedback' "
            f"WHERE id = '{REVIEW_ID}'"
        )
        assert reply.ok, f"vendor reply should succeed: {reply.error}"
        assert _rating(db) == "1"

        # Admins retain full moderation control (guard bypasses has_role('admin')).
        moderate = as_admin.execute(
            f"UPDATE public.reviews SET status = 'removed' WHERE id = '{REVIEW_ID}'"
        )
        assert moderate.ok, f"admin moderation should succeed: {moderate.error}"
    finally:
        _cleanup(db)
