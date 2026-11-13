"""DB-backed coupon money + concurrency tests (disposable local Postgres).

Runs against ``SUPABASE_DB_URL`` (the shared ``db`` fixture from tests.test_ledger
applies every migration into a disposable database and skips when Postgres is
unreachable). Covers:

* atomic redemption reservation — total / per-user limits hold under 12-way
  concurrency, and the monthly platform budget is a hard stop;
* checkout expiry releases reserved uses (and their budget);
* collection ledger legs for platform- vs vendor-funded discounts;
* a full refund of a discounted order nets every account back to zero;
* the birthday greeting function is idempotent per user per year.
"""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from app.services.orders.audit import sql_literal
from tests.rls.conftest import PgConn

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LISTING_A = "b1000000-0000-0000-0000-000000000001"
CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
ACTOR = "66666666-6666-6666-6666-666666666666"

pytestmark = pytest.mark.prepaid_settlement_db


def _ok(db: PgConn, sql: str) -> list[str]:
    result = db.run_script(sql)
    assert result.ok, result.error
    return result.rows


def _scalar(db: PgConn, sql: str) -> str:
    result = db.run(sql)
    assert result.ok, result.error
    return result.rows[-1] if result.rows else ""


def _coupon(
    db: PgConn,
    *,
    funder: str = "platform",
    total_limit: int | None = None,
    per_user_limit: int = 1,
    amount_ngwee: int = 2_000,
) -> str:
    coupon_id = str(uuid.uuid4())
    code = "T" + uuid.uuid4().hex[:10].upper()
    vendor_cols = (
        f"'vendor', '{VENDOR_A}'::uuid, 'vendor', '{VENDOR_A}'::uuid"
        if funder == "vendor"
        else "'platform', NULL, 'all', NULL"
    )
    _ok(
        db,
        f"""
INSERT INTO public.coupons (
  id, code, kind, amount_ngwee, funder, vendor_id, scope, scope_vendor_id,
  starts_at, total_limit, per_user_limit
) VALUES (
  '{coupon_id}', '{code}', 'fixed', {amount_ngwee}, {vendor_cols},
  now() - interval '1 day', {total_limit if total_limit is not None else "NULL"},
  {per_user_limit}
);
""",
    )
    return coupon_id


def _checkout(db: PgConn, *, customer: str = CUSTOMER_A, total: int = 10_000) -> str:
    checkout_id = str(uuid.uuid4())
    _ok(
        db,
        f"""
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  '{checkout_id}', '{customer}', 'chk-{checkout_id}', {total}, 0, {total}, 'pending'
);
""",
    )
    return checkout_id


def _set_budget(db: PgConn, cap: int) -> None:
    _ok(
        db,
        f"""
UPDATE public.platform_config SET value = '{cap}'::jsonb
WHERE key = 'promo_monthly_budget_ngwee';
DELETE FROM public.promo_budgets;
""",
    )


def _reserve(db: PgConn, coupon_id: str, user: str, checkout_id: str, amount: int) -> Any:
    return db.run(
        f"SELECT public.reserve_coupon_redemption('{coupon_id}', '{user}', "
        f"'{checkout_id}', {amount});"
    )


@pytest.fixture(autouse=True)
def generous_budget(db: PgConn) -> None:
    _set_budget(db, 100_000_000)


def test_total_limit_holds_under_concurrency(db: PgConn) -> None:
    coupon_id = _coupon(db, total_limit=3, per_user_limit=50)
    checkouts = [_checkout(db) for _ in range(12)]
    barrier = Barrier(len(checkouts))

    def attempt(checkout_id: str) -> bool:
        barrier.wait()
        return bool(_reserve(db, coupon_id, CUSTOMER_A, checkout_id, 1_000).ok)

    with ThreadPoolExecutor(max_workers=len(checkouts)) as pool:
        outcomes = list(pool.map(attempt, checkouts))

    assert sum(outcomes) == 3
    assert _scalar(db, f"SELECT uses_count FROM public.coupons WHERE id = '{coupon_id}'") == "3"
    assert (
        _scalar(
            db,
            f"SELECT count(*) FROM public.coupon_redemptions "
            f"WHERE coupon_id = '{coupon_id}' AND status = 'reserved'",
        )
        == "3"
    )


def test_per_user_limit_holds_under_concurrency(db: PgConn) -> None:
    coupon_id = _coupon(db, total_limit=None, per_user_limit=1)
    checkouts = [_checkout(db, customer=CUSTOMER_B) for _ in range(8)]
    barrier = Barrier(len(checkouts))

    def attempt(checkout_id: str) -> tuple[bool, str]:
        barrier.wait()
        result = _reserve(db, coupon_id, CUSTOMER_B, checkout_id, 500)
        return result.ok, result.error or ""

    with ThreadPoolExecutor(max_workers=len(checkouts)) as pool:
        outcomes = list(pool.map(attempt, checkouts))

    assert sum(ok for ok, _ in outcomes) == 1
    assert all("COUPON_LIMIT:user" in error for ok, error in outcomes if not ok)


def test_reservation_is_idempotent_for_the_same_checkout(db: PgConn) -> None:
    coupon_id = _coupon(db, total_limit=1)
    checkout_id = _checkout(db)
    first = _reserve(db, coupon_id, CUSTOMER_A, checkout_id, 700)
    again = _reserve(db, coupon_id, CUSTOMER_A, checkout_id, 700)
    assert first.ok and again.ok
    assert first.rows[-1] == again.rows[-1]
    assert _scalar(db, f"SELECT uses_count FROM public.coupons WHERE id = '{coupon_id}'") == "1"


def test_monthly_platform_budget_is_a_hard_stop(db: PgConn) -> None:
    _set_budget(db, 1_000)
    coupon_id = _coupon(db, per_user_limit=10)
    assert _reserve(db, coupon_id, CUSTOMER_A, _checkout(db), 600).ok
    blocked = _reserve(db, coupon_id, CUSTOMER_A, _checkout(db), 600)
    assert not blocked.ok and "COUPON_BUDGET:exhausted" in (blocked.error or "")
    # Vendor-funded coupons never touch the platform budget.
    vendor_coupon = _coupon(db, funder="vendor", per_user_limit=10)
    assert _reserve(db, vendor_coupon, CUSTOMER_A, _checkout(db), 600).ok


def test_checkout_expiry_releases_use_and_budget(db: PgConn) -> None:
    _set_budget(db, 5_000)
    coupon_id = _coupon(db, total_limit=1)
    checkout_id = _checkout(db)
    assert _reserve(db, coupon_id, CUSTOMER_A, checkout_id, 2_000).ok
    _ok(
        db,
        f"SELECT public.expire_checkout_group_if_unpaid('{checkout_id}', 'expired');",
    )
    assert _scalar(db, f"SELECT uses_count FROM public.coupons WHERE id = '{coupon_id}'") == "0"
    assert (
        _scalar(
            db,
            "SELECT status FROM public.coupon_redemptions "
            f"WHERE checkout_group_id = '{checkout_id}'",
        )
        == "released"
    )
    assert _scalar(db, "SELECT coalesce(sum(committed_ngwee), 0) FROM public.promo_budgets") == "0"
    # The use is free again for another checkout.
    assert _reserve(db, coupon_id, CUSTOMER_B, _checkout(db, customer=CUSTOMER_B), 2_000).ok
    audit = _scalar(
        db,
        "SELECT count(*) FROM public.audit_log WHERE action = 'coupon_redemption.transition'",
    )
    assert int(audit) >= 1


def test_transition_guard_refuses_illegal_moves(db: PgConn) -> None:
    coupon_id = _coupon(db)
    checkout_id = _checkout(db)
    redemption = _reserve(db, coupon_id, CUSTOMER_A, checkout_id, 100).rows[-1]
    assert db.run(
        f"SELECT public.coupon_redemption_transition('{redemption}', 'released', NULL, 'test');"
    ).ok
    illegal = db.run(
        f"SELECT public.coupon_redemption_transition('{redemption}', 'applied', NULL, 'test');"
    )
    assert not illegal.ok and "illegal coupon redemption transition" in (illegal.error or "")


# ---------------------------------------------------------------------------
# Collection + refund ledger legs
# ---------------------------------------------------------------------------

ITEMS = 20_000  # 2 x K100
DELIVERY = 3_000
DISCOUNT = 2_000


def _discounted_order(db: PgConn, *, funder: str) -> tuple[str, str, str]:
    coupon_id = _coupon(db, funder=funder, amount_ngwee=DISCOUNT)
    paid = ITEMS + DELIVERY - DISCOUNT
    checkout_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    payment_id = str(uuid.uuid4())
    _ok(
        db,
        f"""
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee,
  status, coupon_id, coupon_code, discount_ngwee
) VALUES (
  '{checkout_id}', '{CUSTOMER_A}', 'chk-{checkout_id}', {ITEMS}, {DELIVERY}, {paid},
  'completed', '{coupon_id}', 'X', {DISCOUNT}
);
SELECT public.reserve_coupon_redemption('{coupon_id}', '{CUSTOMER_A}', '{checkout_id}', {DISCOUNT});
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, delivery_fee_ngwee,
  cod, commission_snapshot, coupon_redemption_id, coupon_discount_ngwee, coupon_funder
) VALUES (
  '{order_id}', '{checkout_id}', '{VENDOR_A}', '{CUSTOMER_A}', 'placed', 'delivery',
  {DELIVERY}, false, '{{"lines": []}}'::jsonb,
  (SELECT id FROM public.coupon_redemptions WHERE checkout_group_id = '{checkout_id}'),
  {DISCOUNT}, '{funder}'
);
INSERT INTO public.order_items (id, order_id, item_kind, qty, unit_price_ngwee)
VALUES ('{item_id}', '{order_id}', 'product', 2, {ITEMS // 2});
INSERT INTO public.payments (
  id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
) VALUES (
  '{payment_id}', '{checkout_id}', 'lenco', 'mtn', 'ord-{payment_id}', {paid}, 'ussd_pushed'
);
""",
    )
    observation = {
        "reference": f"ord-{payment_id}",
        "amount_ngwee": paid,
        "currency": "ZMW",
        "provider_reference": None,
        "source": "coupon_db_test",
    }
    result = db.run(
        f"SELECT public.apply_prepaid_collection_success('{payment_id}', '{ACTOR}', "
        f"'coupon test', {sql_literal(json.dumps(observation))}::jsonb);"
    )
    assert result.ok, result.error
    assert json.loads(result.rows[-1])["result"] == "applied"
    return checkout_id, order_id, payment_id


def _account_total(db: PgConn, kind: str, order_id: str) -> int:
    return int(
        _scalar(
            db,
            f"""
SELECT coalesce(sum(lp.amount_ngwee), 0)
FROM public.ledger_postings lp
JOIN public.ledger_transactions lt ON lt.id = lp.transaction_id
JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE lt.order_id = '{order_id}' AND la.kind = '{kind}';
""",
        )
    )


def test_platform_funded_collection_tops_escrow_up_from_marketing(db: PgConn) -> None:
    checkout_id, order_id, _ = _discounted_order(db, funder="platform")
    paid = ITEMS + DELIVERY - DISCOUNT
    assert _account_total(db, "platform_cash", order_id) == paid  # what Lenco collected
    assert _account_total(db, "marketing_expense", order_id) == DISCOUNT
    # Escrow holds the FULL price, so the vendor's release is unchanged.
    assert _account_total(db, "escrow", order_id) == -(ITEMS + DELIVERY)
    kinds = _scalar(
        db,
        f"SELECT string_agg(kind, ',' ORDER BY kind) FROM public.ledger_transactions "
        f"WHERE order_id = '{order_id}'",
    )
    assert kinds == "coupon_funding,escrow_hold"
    assert (
        _scalar(
            db,
            "SELECT status FROM public.coupon_redemptions "
            f"WHERE checkout_group_id = '{checkout_id}'",
        )
        == "applied"
    )


def test_vendor_funded_collection_is_simply_a_smaller_order(db: PgConn) -> None:
    from app.services.escrow import release as release_mod

    _, order_id, _ = _discounted_order(db, funder="vendor")
    paid = ITEMS + DELIVERY - DISCOUNT
    assert _account_total(db, "escrow", order_id) == -paid
    assert _account_total(db, "marketing_expense", order_id) == 0
    # The vendor's release gross is items − discount.
    assert release_mod._order_gross_ngwee(order_id) == ITEMS - DISCOUNT


def test_platform_funded_release_gross_is_full_price(db: PgConn) -> None:
    from app.services.escrow import release as release_mod

    _, order_id, _ = _discounted_order(db, funder="platform")
    assert release_mod._order_gross_ngwee(order_id) == ITEMS


def test_full_refund_with_platform_discount_nets_to_zero(db: PgConn) -> None:
    from app.services.escrow.release_accounting import remaining_escrow_ngwee
    from app.services.ledger.engine import post_transaction
    from app.services.ledger.templates import LedgerTemplate

    _, order_id, _ = _discounted_order(db, funder="platform")
    assert remaining_escrow_ngwee(order_id) == ITEMS + DELIVERY
    paid = ITEMS + DELIVERY - DISCOUNT
    post_transaction(
        idempotency_key=f"rfd-test-{order_id}",
        template=LedgerTemplate.REFUND_LANE1,
        order_id=order_id,
        refund_ngwee=paid,
        promo_return_ngwee=DISCOUNT,
    )
    assert remaining_escrow_ngwee(order_id) == 0
    for kind in ("escrow", "platform_cash", "marketing_expense"):
        assert _account_total(db, kind, order_id) == 0, kind


def test_full_refund_with_vendor_discount_returns_what_was_paid(db: PgConn) -> None:
    from app.services.escrow.release_accounting import remaining_escrow_ngwee
    from app.services.ledger.engine import post_transaction
    from app.services.ledger.templates import LedgerTemplate

    _, order_id, _ = _discounted_order(db, funder="vendor")
    paid = ITEMS + DELIVERY - DISCOUNT
    assert remaining_escrow_ngwee(order_id) == paid
    post_transaction(
        idempotency_key=f"rfd-test-{order_id}",
        template=LedgerTemplate.REFUND_LANE1,
        order_id=order_id,
        refund_ngwee=paid,
    )
    assert remaining_escrow_ngwee(order_id) == 0
    assert _account_total(db, "platform_cash", order_id) == 0


# ---------------------------------------------------------------------------
# Birthday greeting idempotency
# ---------------------------------------------------------------------------


def test_birthday_greeting_is_issued_once_per_user_per_year(db: PgConn) -> None:
    user = CUSTOMER_B
    year = 2040 + uuid.uuid4().int % 150  # fresh year per run: the DB may be reused
    _ok(
        db,
        f"""
DELETE FROM public.birthday_greetings WHERE user_id = '{user}';
DELETE FROM public.in_app_notifications WHERE recipient_user_id = '{user}'
  AND type = 'birthday_greeting';
DELETE FROM public.notification_outbox WHERE dedupe_key LIKE 'birthday_greeting:{user}:%';
""",
    )

    def issue(code: str) -> Any:
        return db.run(
            f"SELECT public.issue_birthday_greeting('{user}', {year}, '{year}-06-01', '{code}', "
            "2000, 20000, 14);"
        )

    barrier = Barrier(4)

    def concurrent(index: int) -> str:
        barrier.wait()
        result = issue(f"BDAY-TEST{index}{uuid.uuid4().hex[:4].upper()}")
        assert result.ok, result.error
        return result.rows[-1] if result.rows else ""

    with ThreadPoolExecutor(max_workers=4) as pool:
        coupons = [value for value in pool.map(concurrent, range(4)) if value]

    assert len(coupons) == 1
    assert (
        _scalar(
            db,
            f"SELECT count(*) FROM public.coupons WHERE personal_user_id = '{user}' "
            "AND source = 'birthday' "
            f"AND starts_at::date BETWEEN '{year}-05-30' AND '{year}-06-02'",
        )
        == "1"
    )
    assert (
        _scalar(
            db,
            f"SELECT count(*) FROM public.notification_outbox "
            f"WHERE dedupe_key = 'birthday_greeting:{user}:{year}:whatsapp'",
        )
        == "1"
    )
    assert (
        _scalar(
            db,
            f"SELECT count(*) FROM public.in_app_notifications WHERE recipient_user_id = '{user}' "
            f"AND dedupe_key = 'birthday:{year}'",
        )
        == "1"
    )
    # Personal coupon: single use, platform funded, only for that user.
    row = _scalar(
        db,
        f"SELECT total_limit || '|' || per_user_limit || '|' || funder FROM public.coupons "
        f"WHERE id = '{coupons[0]}'",
    )
    assert row == "1|1|platform"


def test_finished_gift_details_are_redacted_once(db: PgConn) -> None:
    from app.routers.internal_gifts import redact_finished_gifts

    checkout_id = _checkout(db)
    _ok(
        db,
        f"""
INSERT INTO public.gift_details (checkout_group_id, buyer_id, recipient_name,
  recipient_phone, message, buyer_attested_at)
VALUES ('{checkout_id}', '{CUSTOMER_A}', 'Mary', '+260971234567', 'Happy day', now());
UPDATE public.checkout_groups SET status = 'expired' WHERE id = '{checkout_id}';
""",
    )
    assert redact_finished_gifts().redacted >= 1
    row = _scalar(
        db,
        "SELECT coalesce(recipient_phone, '-') || '|' || coalesce(message, '-') || '|' "
        f"|| recipient_name FROM public.gift_details WHERE checkout_group_id = '{checkout_id}'",
    )
    assert row == "-|-|Mary"
    # Idempotent: a re-run finds nothing left to redact for this checkout.
    redact_finished_gifts()
    assert (
        _scalar(
            db,
            f"SELECT count(*) FROM public.gift_details WHERE checkout_group_id = '{checkout_id}' "
            "AND redacted_at IS NOT NULL",
        )
        == "1"
    )
