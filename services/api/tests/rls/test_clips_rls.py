"""M17-P01 — clip RLS and the invariants that must live in the database.

These run against live Postgres because the claims they make are claims *about
Postgres*, not about Python. Three in particular cannot be proven any other way:

* a clip that is not ``published`` is invisible to anon — asserted per status, so
  a future status added to the CHECK without a matching policy review fails here;
* a clip may link at most 3 listings and only its **own vendor's** listings —
  enforced by trigger, so it holds for any future endpoint, not just today's;
* the counter columns carry no client UPDATE grant, which is what makes
  "server-managed counters" a privilege fact rather than a convention.

Seeding rides the shared demo fixtures (``tests/fixtures/demo/ids.json``) and role
switching goes through ``RoleSession``, so these behave like every other RLS test
rather than inventing a second harness.
"""

from __future__ import annotations

import uuid

import pytest
from tests.rls.conftest import Persona, PgConn, RoleSession

CLIP_TABLES: tuple[str, ...] = (
    "video_clips",
    "clip_products",
    "clip_likes",
    "clip_comments",
    "clip_reports",
    "clip_views",
)

COUNTER_COLUMNS: tuple[str, ...] = ("like_count", "comment_count", "view_count")

NON_PUBLIC_STATUSES: tuple[str, ...] = (
    "draft",
    "screening",
    "pending_review",
    "rejected",
    "taken_down",
)

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # ids.json vendors.shop_a
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"  # ids.json vendors.shop_b
LISTING_A = "b1000000-0000-0000-0000-000000000001"  # listings.phone_a  (shop_a)
LISTING_B = "b1000000-0000-0000-0000-000000000002"  # listings.chitenge_b (shop_b)
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"


def _as_bool(value: str) -> bool:
    return value.lower() in {"t", "true", "1"}


# --- Structural guarantees --------------------------------------------------
def test_every_clip_table_forces_rls(db: PgConn) -> None:
    """FORCE matters because the API path runs as the table owner.

    Without it an owner session bypasses every policy below, and a bug in one
    router becomes a cross-vendor leak instead of a contained error.
    """
    quoted = ",".join(f"'{t}'" for t in CLIP_TABLES)
    result = db.run(
        f"""
        SELECT c.relname || '|' || c.relrowsecurity || '|' || c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname IN ({quoted})
        ORDER BY 1
        """
    )
    assert result.ok, result.error
    seen: dict[str, tuple[bool, bool]] = {}
    for row in result.rows:
        name, rls_raw, force_raw = row.split("|")
        seen[name] = (_as_bool(rls_raw), _as_bool(force_raw))

    missing = sorted(set(CLIP_TABLES) - set(seen))
    assert not missing, f"clip tables absent from schema: {missing}"
    for table in CLIP_TABLES:
        rls, force = seen[table]
        assert rls, f"{table}: relrowsecurity expected true"
        assert force, f"{table}: relforcerowsecurity expected true"


def test_counter_columns_have_no_client_update_grant(db: PgConn) -> None:
    """The structural half of 'counters are server-managed'.

    Migration 0076 grants column-level UPDATE for editable metadata only. If a
    future migration widens that to a table-level grant this fails — which is
    exactly the regression worth catching, because a client-writable counter lets
    a vendor inflate their own engagement.
    """
    quoted = ",".join(f"'{c}'" for c in COUNTER_COLUMNS)
    result = db.run(
        f"""
        SELECT grantee || '.' || column_name
        FROM information_schema.column_privileges
        WHERE table_schema = 'public'
          AND table_name = 'video_clips'
          AND privilege_type = 'UPDATE'
          AND grantee IN ('anon', 'authenticated')
          AND column_name IN ({quoted})
        ORDER BY 1
        """
    )
    assert result.ok, result.error
    assert result.rows == [], f"counter columns are client-writable: {result.rows}"


def test_status_is_not_client_writable(db: PgConn) -> None:
    """Lifecycle belongs to the guarded transitions, not to a client UPDATE."""
    result = db.run(
        """
        SELECT grantee
        FROM information_schema.column_privileges
        WHERE table_schema = 'public'
          AND table_name = 'video_clips'
          AND privilege_type = 'UPDATE'
          AND grantee IN ('anon', 'authenticated')
          AND column_name = 'status'
        """
    )
    assert result.ok, result.error
    assert result.rows == [], "status must not be client-writable (convention #4)"


def test_duration_cap_is_a_database_check(db: PgConn) -> None:
    """D-V3's <=60s ceiling protects the delivery budget; a preset cannot evade it."""
    result = db.run(
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'public.video_clips'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%duration_s%'
        """
    )
    assert result.ok, result.error
    assert result.rows, "expected a CHECK constraint on duration_s"
    assert "60" in result.rows[0]


def test_the_counter_function_is_not_executable_by_clients(db: PgConn) -> None:
    result = db.run(
        """
        SELECT count(*)::text
        FROM information_schema.routine_privileges
        WHERE routine_schema = 'public'
          AND routine_name = 'clip_bump_counter'
          AND grantee IN ('anon', 'authenticated')
        """
    )
    assert result.ok, result.error
    assert result.rows == ["0"], "clip_bump_counter must be service-role only"


# --- Seed helpers (owner role — bypasses RLS, like the other RLS tests) -----
def _seed_clip(db: PgConn, *, vendor_id: str, status: str) -> str:
    clip_id = str(uuid.uuid4())
    result = db.run(
        f"""
        BEGIN;
        INSERT INTO public.video_clips (id, vendor_id, status, caption, duration_s)
        VALUES ('{clip_id}', '{vendor_id}', '{status}', 'a clip', 20);
        COMMIT;
        """
    )
    assert result.ok, f"clip seed failed: {result.error}"
    return clip_id


def _seed_listing(db: PgConn, *, vendor_id: str) -> str:
    listing_id = str(uuid.uuid4())
    product_id = "b0000000-0000-0000-0000-000000000001"
    result = db.run(
        f"""
        BEGIN;
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, product_class, title_override,
          price_ngwee, condition, stock_mode, status
        )
        VALUES ('{listing_id}', '{vendor_id}', '{product_id}', 'A', 'Clip listing', 150000, 'new',
                'always_available', 'draft');
        COMMIT;
        """
    )
    assert result.ok, f"listing seed failed: {result.error}"
    return listing_id


def _cleanup_clip(db: PgConn, clip_id: str) -> None:
    db.run(f"BEGIN; DELETE FROM public.video_clips WHERE id = '{clip_id}'; COMMIT;")


# --- Public visibility ------------------------------------------------------
@pytest.mark.parametrize("status", NON_PUBLIC_STATUSES)
def test_anon_cannot_see_a_non_published_clip(
    db: PgConn, as_anon: RoleSession, status: str
) -> None:
    """Asserted per status so a new lifecycle state cannot leak by omission."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status=status)
    try:
        result = as_anon.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{clip_id}'"
        )
        assert result.ok, result.error
        assert result.rows == [], f"anon could see a {status} clip"
    finally:
        _cleanup_clip(db, clip_id)


def test_anon_can_see_a_published_clip(db: PgConn, as_anon: RoleSession) -> None:
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        result = as_anon.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{clip_id}'"
        )
        assert result.ok, result.error
        assert result.rows == [clip_id]
    finally:
        _cleanup_clip(db, clip_id)


def test_takedown_hides_the_clip_immediately(
    db: PgConn, as_anon: RoleSession
) -> None:
    """Instant-hide: no cache to invalidate, the policy simply stops matching."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        before = as_anon.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{clip_id}'"
        )
        assert before.ok and before.rows == [clip_id]

        moved = db.run(
            f"BEGIN; UPDATE public.video_clips SET status = 'taken_down' "
            f"WHERE id = '{clip_id}'; COMMIT;"
        )
        assert moved.ok, moved.error

        after = as_anon.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{clip_id}'"
        )
        assert after.ok, after.error
        assert after.rows == [], "a taken-down clip was still publicly visible"
    finally:
        _cleanup_clip(db, clip_id)


# --- clip_products: the two DB-level invariants -----------------------------
def test_a_clip_cannot_link_more_than_three_listings(db: PgConn) -> None:
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="draft")
    listings = [_seed_listing(db, vendor_id=VENDOR_A) for _ in range(4)]
    try:
        for index, listing_id in enumerate(listings[:3]):
            ok = db.run(
                f"""
                BEGIN;
                INSERT INTO public.clip_products (clip_id, listing_id, sort_order)
                VALUES ('{clip_id}', '{listing_id}', {index});
                COMMIT;
                """
            )
            assert ok.ok, f"link {index} should have been allowed: {ok.error}"

        fourth = db.run(
            f"""
            BEGIN;
            INSERT INTO public.clip_products (clip_id, listing_id, sort_order)
            VALUES ('{clip_id}', '{listings[3]}', 0);
            COMMIT;
            """
        )
        assert not fourth.ok, "a 4th link should be refused by the database"
        assert "at most 3" in (fourth.error or "").lower()
    finally:
        _cleanup_clip(db, clip_id)
        for listing_id in listings:
            db.run(
                f"BEGIN; DELETE FROM public.vendor_listings "
                f"WHERE id = '{listing_id}'; COMMIT;"
            )


def test_a_clip_cannot_link_another_vendors_listing(db: PgConn) -> None:
    """The invariant with teeth: no harvesting a rival's add-to-cart traffic.

    Enforced by trigger rather than by the router, so it survives the next
    endpoint someone writes against this table.
    """
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="draft")
    try:
        result = db.run(
            f"""
            BEGIN;
            INSERT INTO public.clip_products (clip_id, listing_id)
            VALUES ('{clip_id}', '{LISTING_B}');
            COMMIT;
            """
        )
        assert not result.ok, "cross-vendor link should be refused by the database"
        assert "does not belong" in (result.error or "").lower()
    finally:
        _cleanup_clip(db, clip_id)


def test_clip_product_link_writes_are_vendor_owned(
    db: PgConn,
    as_customer: RoleSession,
    as_other_vendor: RoleSession,
    as_vendor: RoleSession,
) -> None:
    """A well-formed link proves the policy, not merely a malformed-row error."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="draft")
    listings = [_seed_listing(db, vendor_id=VENDOR_A) for _ in range(3)]
    try:
        owner = as_vendor.execute(
            f"INSERT INTO public.clip_products (clip_id, listing_id, sort_order) "
            f"VALUES ('{clip_id}', '{listings[0]}', 0)"
        )
        assert owner.ok, owner.error

        for label, session, listing_id in (
            ("customer", as_customer, listings[1]),
            ("other_vendor", as_other_vendor, listings[2]),
        ):
            denied = session.execute(
                f"INSERT INTO public.clip_products (clip_id, listing_id, sort_order) "
                f"VALUES ('{clip_id}', '{listing_id}', 0)"
            )
            assert not denied.ok, f"{label} linked a vendor-owned clip"
            assert "row-level security" in (denied.error or "").lower(), denied.error
    finally:
        _cleanup_clip(db, clip_id)
        for listing_id in listings:
            db.run(
                f"BEGIN; DELETE FROM public.vendor_listings "
                f"WHERE id = '{listing_id}'; COMMIT;"
            )


def test_the_same_listing_cannot_be_linked_twice(db: PgConn) -> None:
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="draft")
    try:
        first = db.run(
            f"BEGIN; INSERT INTO public.clip_products (clip_id, listing_id) "
            f"VALUES ('{clip_id}', '{LISTING_A}'); COMMIT;"
        )
        assert first.ok, first.error

        second = db.run(
            f"BEGIN; INSERT INTO public.clip_products (clip_id, listing_id) "
            f"VALUES ('{clip_id}', '{LISTING_A}'); COMMIT;"
        )
        assert not second.ok, "duplicate link should violate the unique constraint"
    finally:
        _cleanup_clip(db, clip_id)


# --- Idempotency by constraint ---------------------------------------------
def test_double_like_is_one_row(db: PgConn) -> None:
    """S5: the primary key IS the dedupe. No application read-then-write."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        first = db.run(
            f"BEGIN; INSERT INTO public.clip_likes (clip_id, user_id) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}'); COMMIT;"
        )
        assert first.ok, first.error

        # ON CONFLICT DO NOTHING is how the API writes it: idempotent, no error.
        second = db.run(
            f"BEGIN; INSERT INTO public.clip_likes (clip_id, user_id) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}') ON CONFLICT DO NOTHING; COMMIT;"
        )
        assert second.ok, second.error

        count = db.run(
            f"SELECT count(*)::text FROM public.clip_likes WHERE clip_id = '{clip_id}'"
        )
        assert count.ok and count.rows == ["1"]
    finally:
        _cleanup_clip(db, clip_id)


def test_duplicate_report_is_one_row(db: PgConn) -> None:
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        first = db.run(
            f"BEGIN; INSERT INTO public.clip_reports (clip_id, reporter_id, reason) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}', 'spam'); COMMIT;"
        )
        assert first.ok, first.error

        second = db.run(
            f"BEGIN; INSERT INTO public.clip_reports (clip_id, reporter_id, reason) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}', 'again') ON CONFLICT DO NOTHING; COMMIT;"
        )
        assert second.ok, second.error

        count = db.run(
            f"SELECT count(*)::text FROM public.clip_reports WHERE clip_id = '{clip_id}'"
        )
        assert count.ok and count.rows == ["1"]
    finally:
        _cleanup_clip(db, clip_id)


def test_same_user_same_day_view_is_one_row(db: PgConn) -> None:
    """The '>=3s, deduped per user per day' rule, expressed as a unique key."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        for _ in range(3):
            result = db.run(
                f"BEGIN; INSERT INTO public.clip_views (clip_id, user_id) "
                f"VALUES ('{clip_id}', '{CUSTOMER_A}') ON CONFLICT DO NOTHING; COMMIT;"
            )
            assert result.ok, result.error

        count = db.run(
            f"SELECT count(*)::text FROM public.clip_views WHERE clip_id = '{clip_id}'"
        )
        assert count.ok and count.rows == ["1"]
    finally:
        _cleanup_clip(db, clip_id)


def test_the_same_user_can_view_again_the_next_day(db: PgConn) -> None:
    """Dedupe is per day, not forever — otherwise view counts would flatline."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        today = db.run(
            f"BEGIN; INSERT INTO public.clip_views (clip_id, user_id) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}'); COMMIT;"
        )
        assert today.ok, today.error

        tomorrow = db.run(
            f"BEGIN; INSERT INTO public.clip_views (clip_id, user_id, viewed_on) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}', "
            f"(now() at time zone 'utc')::date + 1); COMMIT;"
        )
        assert tomorrow.ok, tomorrow.error

        count = db.run(
            f"SELECT count(*)::text FROM public.clip_views WHERE clip_id = '{clip_id}'"
        )
        assert count.ok and count.rows == ["2"]
    finally:
        _cleanup_clip(db, clip_id)


# --- Cross-vendor isolation -------------------------------------------------
def test_vendor_a_cannot_read_vendor_bs_draft(
    db: PgConn, as_vendor: RoleSession
) -> None:
    rival_clip = _seed_clip(db, vendor_id=VENDOR_B, status="draft")
    try:
        result = as_vendor.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{rival_clip}'"
        )
        assert result.ok, result.error
        assert result.rows == [], "vendor A could read vendor B's draft clip"
    finally:
        _cleanup_clip(db, rival_clip)


def test_a_vendor_can_read_their_own_draft(
    db: PgConn, as_vendor: RoleSession
) -> None:
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="draft")
    try:
        result = as_vendor.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{clip_id}'"
        )
        assert result.ok, result.error
        assert result.rows == [clip_id]
    finally:
        _cleanup_clip(db, clip_id)


def test_a_vendor_cannot_see_who_reported_their_clip(
    db: PgConn, as_vendor: RoleSession
) -> None:
    """Deliberate: showing a vendor their reporters invites retaliation."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="published")
    try:
        filed = db.run(
            f"BEGIN; INSERT INTO public.clip_reports (clip_id, reporter_id, reason) "
            f"VALUES ('{clip_id}', '{CUSTOMER_A}', 'counterfeit'); COMMIT;"
        )
        assert filed.ok, filed.error

        result = as_vendor.execute(
            f"SELECT reporter_id FROM public.clip_reports WHERE clip_id = '{clip_id}'"
        )
        assert result.ok, result.error
        assert result.rows == [], "the clip owner could see their reporter"
    finally:
        _cleanup_clip(db, clip_id)


def test_an_admin_sees_every_clip_status(db: PgConn, as_admin: RoleSession) -> None:
    """The moderation queue in M17-P07 depends on this."""
    clip_id = _seed_clip(db, vendor_id=VENDOR_A, status="pending_review")
    try:
        result = as_admin.execute(
            f"SELECT id FROM public.video_clips WHERE id = '{clip_id}'"
        )
        assert result.ok, result.error
        assert result.rows == [clip_id]
    finally:
        _cleanup_clip(db, clip_id)


def test_personas_are_the_shared_fixture_users() -> None:
    """Guards the constants above against a fixture-id change."""
    from tests.rls.conftest import PERSONA_UIDS

    assert PERSONA_UIDS[Persona.CUSTOMER] == CUSTOMER_A
