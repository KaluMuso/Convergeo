-- Vendor sourcing hub (docs/plan/vendor-sourcing-hub.md).
--
-- Additive and reversible. NOT applied to any database by the PR that adds it.
--   * vendors.supplier_types          -- owner-declared supplier kinds (empty = not listed)
--   * vendor_listings.made_in_zambia  -- self-declared flag (default false)
--   * import_requests / import_request_quotes -- curated import path. DATA ONLY:
--     no payment, order, ledger or escrow row is ever created from these tables.
--
-- RLS: enabled + forced on both new tables. Clients may only SELECT (owner: own
-- rows; admin: all). Every write is API-only (service role + admin audit_log).
--
-- Reversal (nothing else depends on these objects):
--   drop table public.import_request_quotes, public.import_requests;
--   alter table public.vendor_listings drop column made_in_zambia;
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
  add column if not exists made_in_zambia boolean not null default false;

comment on column public.vendor_listings.made_in_zambia is
  'Self-declared Made in Zambia flag (admin may unset). Drives the sourcing hub tab.';

create index if not exists vendor_listings_made_in_zambia_idx
  on public.vendor_listings (status)
  where made_in_zambia;

-- ---------------------------------------------------------------------------
-- import_requests
-- ---------------------------------------------------------------------------
create table public.import_requests (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  requested_by uuid not null references auth.users (id) on delete restrict,
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
  quoted_by uuid not null references auth.users (id) on delete restrict,
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
