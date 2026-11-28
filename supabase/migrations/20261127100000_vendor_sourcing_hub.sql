-- Vendor sourcing hub (docs/plan/vendor-sourcing-hub.md).
--
-- Additive and reversible. NOT applied to any database by the PR that adds it.
--   * vendors.supplier_types          -- owner-declared supplier kinds (empty = not listed)
--   * vendor_listings.made_in_zambia_* -- vendor CLAIM + admin APPROVAL (claimed /
--     approved / rejected, optional PACRA/ZABS reference, reviewer, timestamp).
--     Only 'approved' is public in the hub. A guard trigger blocks vendors (RLS
--     owner-update policy) from approving their own claim.
--   * import_requests / import_request_quotes -- curated import path. DATA ONLY:
--     no payment, order, ledger or escrow row is ever created from these tables.
--
-- RLS: enabled + forced on both new tables. Clients may only SELECT (owner: own
-- rows; admin: all). Every write is API-only (service role + admin audit_log).
--
-- Reversal (nothing else depends on these objects):
--   drop table public.import_request_quotes, public.import_requests;
--   drop trigger if exists vendor_listings_made_in_zambia_guard on public.vendor_listings;
--   drop function if exists public.vendor_listings_made_in_zambia_guard();
--   drop index if exists public.vendor_listings_made_in_zambia_idx;
--   alter table public.vendor_listings
--     drop column made_in_zambia_status, drop column made_in_zambia_reference,
--     drop column made_in_zambia_claimed_at, drop column made_in_zambia_reviewed_by,
--     drop column made_in_zambia_reviewed_at, drop column made_in_zambia_review_note;
--   alter table public.vendors drop column supplier_types;

alter table public.vendors
  add column if not exists supplier_types text[] not null default '{}';

alter table public.vendors
  drop constraint if exists vendors_supplier_types_check;
alter table public.vendors
  add constraint vendors_supplier_types_check
  check (
    supplier_types <@ array['wholesaler', 'manufacturer', 'importer', 'service_provider']::text[]
  );

comment on column public.vendors.supplier_types is
  'Owner-declared supplier kinds for the vendor sourcing hub. Empty = not listed as a supplier.';

alter table public.vendor_listings
  add column if not exists made_in_zambia_status text
    check (made_in_zambia_status is null or made_in_zambia_status in ('claimed', 'approved', 'rejected')),
  add column if not exists made_in_zambia_reference text
    check (made_in_zambia_reference is null or char_length(btrim(made_in_zambia_reference)) between 3 and 80),
  add column if not exists made_in_zambia_claimed_at timestamptz,
  add column if not exists made_in_zambia_reviewed_by uuid references auth.users (id) on delete set null,
  add column if not exists made_in_zambia_reviewed_at timestamptz,
  add column if not exists made_in_zambia_review_note text
    check (made_in_zambia_review_note is null or char_length(made_in_zambia_review_note) <= 500);

comment on column public.vendor_listings.made_in_zambia_status is
  'Made in Zambia claim state. NULL = no claim. Only approved is shown in the sourcing hub.';
comment on column public.vendor_listings.made_in_zambia_reference is
  'Optional PACRA / ZABS reference supplied by the vendor with the claim.';

create index if not exists vendor_listings_made_in_zambia_idx
  on public.vendor_listings (updated_at desc)
  where made_in_zambia_status = 'approved';
create index if not exists vendor_listings_made_in_zambia_claimed_idx
  on public.vendor_listings (made_in_zambia_claimed_at)
  where made_in_zambia_status = 'claimed';

-- Guard: owners hold an UPDATE policy on vendor_listings, so the database (not only
-- the API) must stop a vendor approving their own claim. Reviewer fields are written
-- by the admin API (service role) only.
create or replace function public.vendor_listings_made_in_zambia_guard()
returns trigger
language plpgsql
as $$
declare
  privileged boolean :=
    coalesce(auth.role(), '') = 'service_role'
    or current_user in ('postgres', 'supabase_admin', 'service_role');
  old_status text := case when tg_op = 'UPDATE' then old.made_in_zambia_status end;
begin
  if tg_op = 'INSERT' and not privileged and new.made_in_zambia_status is not null then
    raise exception 'made_in_zambia claim must be filed through the API'
      using errcode = '42501';
  end if;

  if not privileged and tg_op = 'UPDATE' then
    if new.made_in_zambia_reviewed_by is distinct from old.made_in_zambia_reviewed_by
       or new.made_in_zambia_reviewed_at is distinct from old.made_in_zambia_reviewed_at
       or new.made_in_zambia_review_note is distinct from old.made_in_zambia_review_note then
      raise exception 'made_in_zambia review fields are admin-only' using errcode = '42501';
    end if;
    if new.made_in_zambia_status is distinct from old_status
       and new.made_in_zambia_status in ('approved', 'rejected') then
      raise exception 'made_in_zambia approval is admin-only' using errcode = '42501';
    end if;
  end if;

  -- A decided claim is frozen for owners: editing the evidence (reference or claim
  -- timestamp) after a decision drops the claim back to 'claimed' for re-review, so
  -- an approved badge can never silently point at changed evidence.
  if not privileged and tg_op = 'UPDATE'
     and old_status in ('approved', 'rejected')
     and new.made_in_zambia_status is not distinct from old_status
     and (new.made_in_zambia_reference is distinct from old.made_in_zambia_reference
          or new.made_in_zambia_claimed_at is distinct from old.made_in_zambia_claimed_at) then
    new.made_in_zambia_status := 'claimed';
  end if;

  if new.made_in_zambia_status in ('approved', 'rejected')
     and (new.made_in_zambia_reviewed_by is null or new.made_in_zambia_reviewed_at is null)
     and (tg_op = 'INSERT' or new.made_in_zambia_status is distinct from old_status) then
    raise exception 'made_in_zambia decision needs reviewer and timestamp'
      using errcode = '23514';
  end if;

  if new.made_in_zambia_status is null or new.made_in_zambia_status = 'claimed' then
    new.made_in_zambia_reviewed_by := null;
    new.made_in_zambia_reviewed_at := null;
    new.made_in_zambia_review_note := null;
  end if;
  if new.made_in_zambia_status is null then
    new.made_in_zambia_reference := null;
    new.made_in_zambia_claimed_at := null;
  end if;
  return new;
end;
$$;

drop trigger if exists vendor_listings_made_in_zambia_guard on public.vendor_listings;
create trigger vendor_listings_made_in_zambia_guard
  before insert or update on public.vendor_listings
  for each row execute function public.vendor_listings_made_in_zambia_guard();

-- ---------------------------------------------------------------------------
-- import_requests
-- ---------------------------------------------------------------------------
create table public.import_requests (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  -- Nullable + SET NULL so account erasure is never blocked by a request row.
  requested_by uuid references auth.users (id) on delete set null,
  title text not null check (char_length(btrim(title)) between 3 and 120),
  description text check (description is null or char_length(description) <= 2000),
  reference_url text check (
    reference_url is null
    or (reference_url ~ '^https://[^\s]+$' and char_length(reference_url) <= 500)
  ),
  image_urls text[] not null default '{}'
    check (cardinality(image_urls) <= 5),
  quantity integer not null check (quantity between 1 and 1000000),
  unit text not null default 'pcs' check (char_length(btrim(unit)) between 1 and 20),
  target_unit_price_ngwee bigint check (
    target_unit_price_ngwee is null or target_unit_price_ngwee > 0
  ),
  destination_city text check (
    destination_city is null or char_length(btrim(destination_city)) between 2 and 60
  ),
  status text not null default 'submitted'
    check (status in ('submitted', 'in_review', 'quoted', 'closed', 'cancelled')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

comment on table public.import_requests is
  'Vendor request to import an overseas product. Data only: no payment or order is created.';

create index import_requests_vendor_idx
  on public.import_requests (vendor_id, created_at desc);
create index import_requests_status_idx
  on public.import_requests (status, created_at desc);

create trigger import_requests_set_updated_at
  before update on public.import_requests
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- import_request_quotes — admin/partner landed-cost ESTIMATES in ngwee
-- ---------------------------------------------------------------------------
create table public.import_request_quotes (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.import_requests (id) on delete cascade,
  quoted_by uuid references auth.users (id) on delete set null,
  partner_label text check (partner_label is null or char_length(btrim(partner_label)) <= 80),
  product_ngwee bigint not null check (product_ngwee >= 0),
  freight_ngwee bigint not null check (freight_ngwee >= 0),
  duty_ngwee bigint not null check (duty_ngwee >= 0),
  clearing_ngwee bigint not null check (clearing_ngwee >= 0),
  other_ngwee bigint not null default 0 check (other_ngwee >= 0),
  total_ngwee bigint generated always as (
    product_ngwee + freight_ngwee + duty_ngwee + clearing_ngwee + other_ngwee
  ) stored,
  lead_time_days integer check (lead_time_days is null or lead_time_days between 1 and 365),
  valid_until timestamptz,
  notes text check (notes is null or char_length(notes) <= 2000),
  -- MVP: every figure is an estimate, never an offer. Relax only with a new decision.
  is_estimate boolean not null default true check (is_estimate),
  created_at timestamptz not null default timezone('utc', now())
);

comment on table public.import_request_quotes is
  'Landed-cost ESTIMATE lines (ngwee) for an import request. Not an offer; no payment.';

create index import_request_quotes_request_idx
  on public.import_request_quotes (request_id, created_at desc);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.import_requests enable row level security;
alter table public.import_requests force row level security;
alter table public.import_request_quotes enable row level security;
alter table public.import_request_quotes force row level security;

revoke all on public.import_requests from public, anon, authenticated;
revoke all on public.import_request_quotes from public, anon, authenticated;
grant select on public.import_requests to authenticated;
grant select on public.import_request_quotes to authenticated;
grant all on public.import_requests to service_role;
grant all on public.import_request_quotes to service_role;

create policy import_requests_select_own_or_admin
  on public.import_requests
  for select
  to authenticated
  using (
    public.has_role('admin')
    or exists (
      select 1 from public.vendors v
      where v.id = import_requests.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy import_request_quotes_select_own_or_admin
  on public.import_request_quotes
  for select
  to authenticated
  using (
    public.has_role('admin')
    or exists (
      select 1
      from public.import_requests r
      join public.vendors v on v.id = r.vendor_id
      where r.id = import_request_quotes.request_id
        and v.owner_user_id = (select auth.uid())
    )
  );
