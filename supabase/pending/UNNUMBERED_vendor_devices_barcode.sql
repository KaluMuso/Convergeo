-- Vendor mobile app support: push device tokens + per-vendor barcodes.
--
-- UNNUMBERED on purpose: it must be renamed to <timestamp>_vendor_devices_barcode.sql and
-- registered in every migration inventory only AFTER the migration chain (#973 to #996)
-- has landed. Until then it lives in supabase/pending/ so replay, typegen and the
-- migration count are untouched.
--
--   public.device_tokens       Expo push tokens, one row per physical device token.
--   public.vendor_listings.barcode   optional retail barcode, unique per vendor.
--
-- Security model
--   * RLS ENABLE + FORCE on device_tokens. An authenticated user may SELECT only
--     their own rows (user_id = auth.uid()). No client INSERT / UPDATE / DELETE grant:
--     every write is made by the API with the service role (POST/DELETE /vendor/devices).
--   * Sending pushes is a service-role action; the token column is never exposed
--     through a public view.
--   * The barcode lives on vendor_listings, whose existing RLS applies unchanged.
--
-- Additive only. Reversible:
--   drop index if exists public.vendor_listings_vendor_barcode_key;
--   alter table public.vendor_listings drop column if exists barcode;
--   drop table if exists public.device_tokens;

create table public.device_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  token text not null check (char_length(token) between 20 and 200),
  platform text not null check (platform in ('android', 'ios')),
  app_version text check (app_version is null or char_length(app_version) <= 32),
  last_seen_at timestamptz not null default timezone('utc', now()),
  revoked_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  constraint device_tokens_token_key unique (token)
);

comment on table public.device_tokens is
  'Expo push tokens for the vendor mobile app. Written only by the API (service role). Owner may read their own rows; revoked_at set on sign-out or when more than 10 active tokens exist for a vendor.';

create index device_tokens_vendor_active_idx
  on public.device_tokens (vendor_id, last_seen_at desc)
  where revoked_at is null;

alter table public.device_tokens enable row level security;
alter table public.device_tokens force row level security;

revoke all on public.device_tokens from public, anon, authenticated;
grant select on public.device_tokens to authenticated;
grant select, insert, update, delete on public.device_tokens to service_role;

create policy device_tokens_owner_select on public.device_tokens
  for select to authenticated
  using (user_id = (select auth.uid()));

alter table public.vendor_listings
  add column if not exists barcode text
    check (barcode is null or barcode ~ '^[0-9A-Za-z-]{4,64}$');

create unique index if not exists vendor_listings_vendor_barcode_key
  on public.vendor_listings (vendor_id, barcode)
  where barcode is not null;

comment on column public.vendor_listings.barcode is
  'Optional retail barcode (EAN/UPC/Code128 text), unique per vendor when set. Used by the vendor mobile scanner.';
