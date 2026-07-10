-- 0021_vendor_payout_method.sql
-- M12-P08: Vendor payout destination override + fraud-hold after MoMo number change.
-- Additive nullable columns on vendors; payout execution (M08-P09) reads payout_msisdn
-- when set, else falls back to approved KYC momo_name_match.
--
-- Reversible:
--   alter table public.vendors drop constraint if exists vendors_payout_rail_check;
--   alter table public.vendors
--     drop column if exists payout_msisdn,
--     drop column if exists payout_rail,
--     drop column if exists payout_hold_until;

alter table public.vendors
  add column if not exists payout_msisdn text,
  add column if not exists payout_rail text,
  add column if not exists payout_hold_until timestamptz;

alter table public.vendors
  drop constraint if exists vendors_payout_rail_check;

alter table public.vendors
  add constraint vendors_payout_rail_check
  check (payout_rail in ('mtn', 'airtel', 'zamtel') or payout_rail is null);

comment on column public.vendors.payout_msisdn is
  'Vendor-selected MoMo payout destination; overrides KYC momo_name_match when set (M12-P08).';
comment on column public.vendors.payout_rail is
  'MoMo operator for payout_msisdn (mtn/airtel/zamtel).';
comment on column public.vendors.payout_hold_until is
  'When set and in the future, payout initiation is blocked (24h hold after method change).';
