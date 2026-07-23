-- Staging money-drill fixtures (S1–S3): prepare the LIVE Vergeo5 project for a
-- Lenco SANDBOX collection → ledger → release → payout walk.
--
-- ⚠ SANDBOX PAYMENTS ONLY. Apply only when the API host has LENCO_ENV=sandbox +
--   PAYMENTS_ENABLED=true and PAYMENTS_ALLOW_PRODUCTION UNSET. Never with prod
--   Lenco keys. `public_launch` must remain false.
--   Runbook: docs/production-readiness/2026-07-22/money-drill-runbook.md
--
-- Idempotent + reversible (rollback blocks at the bottom). If the seeded listing
-- IDs are absent (a fresh isolated DB), every statement is a safe 0-row no-op.
-- Do NOT run against an isolated staging DB that already has real non-demo stock.
--
-- The BUYER cannot be fixtured — Supabase Auth phone-OTP creates auth.users and
-- the profile via the on_auth_user_created trigger. Sign in as a throwaway
-- staging buyer instead (operator step).

begin;

-- ── Section 1 — Catalog visibility ───────────────────────────────────────────
-- Move five COD-eligible retail listings off the `demo/` Cloudinary public_id
-- prefix so the FD-04 / VC-P06 demo-exclusion doesn't hide them from catalog +
-- search. Images may 404 until the assets are renamed/copied to `staging-drill/`;
-- checkout and cart do not require images.
with drill as (
  select vl.id
  from public.vendor_listings vl
  where vl.id in (
    'b904645c-ed91-1329-72e3-43d7868855fe', -- tea-coffee-standard (K28.97) — primary drill SKU
    '7cbffa47-c958-410b-ae32-e341d6b52fa3', -- flour-baking-standard
    '0b33171a-468c-ecec-71c1-61f96ca48076', -- cooking-oil-5l
    '388660b1-40c5-d004-7bde-f9c532686c67', -- footwear-premium
    'cef8e01d-4184-5e19-9fcf-732d7166a39b'  -- beverages-standard
  )
  and vl.status = 'active'
  and coalesce(vl.wholesale, false) = false
  and vl.price_ngwee > 0
  and vl.price_ngwee <= 50000 -- COD ≤ K500
)
update public.listing_images li
set
  cloudinary_public_id = regexp_replace(li.cloudinary_public_id, '^demo/', 'staging-drill/'),
  updated_at = now()
from drill
where li.listing_id = drill.id
  and li.cloudinary_public_id ilike 'demo/%';

-- ── Section 2 — Stock ────────────────────────────────────────────────────────
-- Ensure the drill listings carry healthy TRACKED stock so checkout can reserve
-- and the oversell-safe path is exercised. `greatest(coalesce(...,0),100)` never
-- reduces existing stock ≥100; it bumps NULL/untracked or low stock up to 100.
update public.vendor_listings vl
set stock_qty = greatest(coalesce(vl.stock_qty, 0), 100)
where vl.id in (
  'b904645c-ed91-1329-72e3-43d7868855fe',
  '7cbffa47-c958-410b-ae32-e341d6b52fa3',
  '0b33171a-468c-ecec-71c1-61f96ca48076',
  '388660b1-40c5-d004-7bde-f9c532686c67',
  'cef8e01d-4184-5e19-9fcf-732d7166a39b'
)
and vl.status = 'active';

-- ── Section 3 — Vendor payout destination (release → payout leg) ──────────────
-- Set a SANDBOX MoMo payout destination on the vendor(s) that own the drill
-- listings and clear any 24h fraud-hold, so `retry_pending_payouts` can send the
-- transfer. payout_rail ∈ (mtn|airtel|zamtel). Payout execution reads
-- payout_msisdn when set (M12-P08), else falls back to the approved KYC momo.
-- This does NOT change vendor `status`/`kyc_tier` (server-controlled), so the
-- guard_vendor_status_update trigger is not tripped.
--
-- 0961111111 is the sandbox MTN *collection* success number; if Lenco's sandbox
-- rejects it for /transfers, replace it with a sandbox transfer destination.
update public.vendors v
set payout_msisdn = '0961111111',
    payout_rail = 'mtn',
    payout_hold_until = null
where v.status = 'active'
  and v.id in (
    select distinct vl.vendor_id
    from public.vendor_listings vl
    where vl.id in (
      'b904645c-ed91-1329-72e3-43d7868855fe',
      '7cbffa47-c958-410b-ae32-e341d6b52fa3',
      '0b33171a-468c-ecec-71c1-61f96ca48076',
      '388660b1-40c5-d004-7bde-f9c532686c67',
      'cef8e01d-4184-5e19-9fcf-732d7166a39b'
    )
  );

commit;

-- ── Verify (run separately; read-only) ───────────────────────────────────────
-- Primary drill SKU is active, priced for COD, in stock, with a payout-ready vendor:
--   select vl.id, vl.price_ngwee, vl.stock_qty, vl.status,
--          v.status as vendor_status, v.payout_msisdn, v.payout_rail, v.payout_hold_until
--   from public.vendor_listings vl
--   join public.vendors v on v.id = vl.vendor_id
--   where vl.id = 'b904645c-ed91-1329-72e3-43d7868855fe';
-- Commission config present (release computes commission_capture from these bps):
--   select category_key, rate_bps from public.commission_rates order by category_key;
-- COD cap (drill SKU price must be ≤ this):
--   select value from public.platform_config where key = 'cod_cap_ngwee';
-- Money plane is still empty pre-drill (baseline for the run):
--   select
--     (select count(*) from public.payments)             as payments,
--     (select count(*) from public.ledger_transactions)  as ledger_txns,
--     (select count(*) from public.orders)               as orders,
--     (select count(*) from public.payouts)              as payouts;

-- ── Rollback ─────────────────────────────────────────────────────────────────
-- Section 1 (catalog):
--   update public.listing_images
--   set cloudinary_public_id = regexp_replace(cloudinary_public_id, '^staging-drill/', 'demo/'),
--       updated_at = now()
--   where cloudinary_public_id ilike 'staging-drill/%';
-- Section 3 (payout method):
--   update public.vendors set payout_msisdn = null, payout_rail = null, payout_hold_until = null
--   where id in (select distinct vendor_id from public.vendor_listings where id in (
--     'b904645c-ed91-1329-72e3-43d7868855fe','7cbffa47-c958-410b-ae32-e341d6b52fa3',
--     '0b33171a-468c-ecec-71c1-61f96ca48076','388660b1-40c5-d004-7bde-f9c532686c67',
--     'cef8e01d-4184-5e19-9fcf-732d7166a39b'));
-- Section 2 (stock) is operational state — reset manually only if needed.
