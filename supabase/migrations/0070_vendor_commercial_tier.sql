-- Commercial subscription tier (D3: billing gated by feature_flags.paid_tiers).
-- Nullable at launch — NULL displays as Bronze (free tier). Distinct from kyc_tier / trust ladder.

alter table public.vendors
  add column if not exists commercial_tier text;

alter table public.vendors
  drop constraint if exists vendors_commercial_tier_check;

alter table public.vendors
  add constraint vendors_commercial_tier_check
  check (
    commercial_tier is null
    or commercial_tier in ('bronze', 'silver', 'gold', 'platinum')
  );

comment on column public.vendors.commercial_tier is
  'Paid vendor subscription tier (bronze/silver/gold/platinum). NULL = free/bronze at launch. Not KYC.';
