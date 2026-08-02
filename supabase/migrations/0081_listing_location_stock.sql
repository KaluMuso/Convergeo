-- R02-P08 — per-branch stock.
--
-- Stock has been listing-level since 0003 (`vendor_listings.stock_mode` /
-- `stock_qty`), so a vendor with two branches has ONE pooled number. In a
-- pickup-first market that is not a rounding error: a customer can be promised
-- an item that is physically at the branch they are not travelling to.
--
-- AUTHORITY RULE (read this before touching the claim path):
--   * a listing WITH rows in listing_location_stock is branch-tracked, and
--     those rows are authoritative;
--   * a listing WITHOUT rows behaves exactly as it does today, off
--     vendor_listings.stock_qty.
-- vendor_listings.stock_qty is deliberately NOT dropped here. Dropping it
-- would rewrite every existing claim, release and revalidate path in one
-- migration, which is precisely the change you do not want to make blind on a
-- money-adjacent surface. It stays as the legacy/pooled value.
--
-- Concurrency follows the existing house pattern in
-- app/services/stock/claim.py: a single conditional UPDATE whose WHERE clause
-- carries the `>= qty` predicate. The row lock plus the predicate ARE the
-- guard — no advisory lock, and deliberately no denormalised counter (M10-P13
-- records why: a maintained counter must be kept true across every claim,
-- void and release path or it silently mis-gates).

create table if not exists public.listing_location_stock (
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  location_id uuid not null references public.vendor_locations (id) on delete cascade,
  stock_qty integer not null default 0 check (stock_qty >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (listing_id, location_id)
);

comment on table public.listing_location_stock is
  'Per-branch stock. When a listing has rows here they are authoritative; a listing with none falls back to vendor_listings.stock_qty (R02-P08).';
comment on column public.listing_location_stock.stock_qty is
  'Units available at this branch. Never client-writable: moved only by the guarded claim/release path.';

create index if not exists listing_location_stock_location_idx
  on public.listing_location_stock (location_id);

drop trigger if exists listing_location_stock_set_updated_at on public.listing_location_stock;
create trigger listing_location_stock_set_updated_at
  before update on public.listing_location_stock
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- A branch must belong to the listing's own vendor.
-- ---------------------------------------------------------------------------
-- Enforced in the database rather than the router, for the same reason M17's
-- clip_products_guard is: a router can be bypassed by the next endpoint
-- someone writes, and stock pointed at a rival's branch would let a vendor
-- draw traffic and pickups to premises they do not own.
create or replace function public.listing_location_stock_guard()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  listing_vendor uuid;
  location_vendor uuid;
begin
  select vendor_id into listing_vendor
  from public.vendor_listings where id = new.listing_id;

  select vendor_id into location_vendor
  from public.vendor_locations where id = new.location_id;

  if listing_vendor is null or location_vendor is null
     or listing_vendor <> location_vendor then
    raise exception
      'listing_location_stock: branch % does not belong to the listing''s vendor',
      new.location_id;
  end if;

  return new;
end;
$$;

drop trigger if exists listing_location_stock_guard_trg on public.listing_location_stock;
create trigger listing_location_stock_guard_trg
  before insert or update on public.listing_location_stock
  for each row
  execute function public.listing_location_stock_guard();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.listing_location_stock enable row level security;
alter table public.listing_location_stock force row level security;

-- Public read: customers must see which branch actually has the item, but only
-- for an active listing whose branch is itself active (R02-P07 status).
drop policy if exists listing_location_stock_public_select on public.listing_location_stock;
create policy listing_location_stock_public_select
  on public.listing_location_stock
  for select
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendor_locations loc on loc.id = listing_location_stock.location_id
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_location_stock.listing_id
        and vl.status = 'active'
        and loc.status = 'active'
        and v.status = 'active'
    )
  );

drop policy if exists listing_location_stock_owner_select on public.listing_location_stock;
create policy listing_location_stock_owner_select
  on public.listing_location_stock
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_location_stock.listing_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy listing_location_stock_public_select on public.listing_location_stock is
  'Per-branch availability is public only for an active listing at an active branch of an active vendor.';

-- No INSERT/UPDATE/DELETE policy for `authenticated` on purpose: quantities move
-- through the service-role claim/release path only. A vendor edits stock via the
-- API, which audits it; direct client writes would bypass that entirely.
revoke all on public.listing_location_stock from anon, authenticated;
grant select on public.listing_location_stock to anon, authenticated;

-- ---------------------------------------------------------------------------
-- Backfill: give every tracked listing a branch row on its vendor's PRIMARY
-- location (R02-P07 guarantees at most one, and backfilled one where any
-- location existed).
-- ---------------------------------------------------------------------------
-- Idempotent: ON CONFLICT DO NOTHING, so replaying never doubles a quantity.
-- A listing whose vendor has no location at all is skipped and keeps its
-- legacy pooled behaviour, which is the correct outcome rather than inventing
-- a branch for it.
insert into public.listing_location_stock (listing_id, location_id, stock_qty)
select vl.id, loc.id, coalesce(vl.stock_qty, 0)
from public.vendor_listings vl
join public.vendor_locations loc
  on loc.vendor_id = vl.vendor_id
 and loc.is_primary
where vl.stock_mode = 'tracked'
on conflict (listing_id, location_id) do nothing;
