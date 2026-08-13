-- Product Strategy core contract.
--
-- This migration is deliberately additive.  Existing A-class catalogue rows keep
-- their current behaviour; new product classes, price modes and trust controls
-- are constrained at the database boundary before their UI flows are enabled.

-- ---------------------------------------------------------------------------
-- Canonical products and variant/commodity modelling
-- ---------------------------------------------------------------------------

alter table public.products
  add column if not exists product_class char(1) not null default 'A',
  add column if not exists sale_unit text not null default 'each',
  add column if not exists base_unit text not null default 'each',
  add column if not exists base_units_per_sale_unit_milli integer not null default 1000,
  add column if not exists commodity_key text,
  add column if not exists commodity_grade text,
  add column if not exists phase integer not null default 1;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'products_product_class_check') then
    alter table public.products add constraint products_product_class_check
      check (product_class in ('A', 'B', 'C'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'products_sale_base_unit_check') then
    alter table public.products add constraint products_sale_base_unit_check
      check (
        sale_unit in ('each', 'metre', 'kg', 'litre', 'bag', 'sqm', 'bunch', 'pile', 'pack', 'case', 'dozen', 'tray', 'pair', 'tonne', 'thousand')
        and base_unit in ('each', 'metre', 'kg', 'litre', 'bag', 'sqm', 'bunch', 'pile', 'pack', 'case', 'dozen', 'tray', 'pair', 'tonne', 'thousand')
        and base_units_per_sale_unit_milli > 0
      );
  end if;
  if not exists (select 1 from pg_constraint where conname = 'products_phase_check') then
    alter table public.products add constraint products_phase_check check (phase between 1 and 3);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'products_class_c_commodity_check') then
    alter table public.products add constraint products_class_c_commodity_check
      check (
        product_class <> 'C'
        or (nullif(btrim(commodity_key), '') is not null and nullif(btrim(commodity_grade), '') is not null)
      ) not valid;
  end if;
end
$$;

create unique index if not exists products_commodity_grade_sale_unit_unique
  on public.products (lower(commodity_key), lower(commodity_grade), sale_unit)
  where product_class = 'C';

create table if not exists public.product_variant_groups (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products (id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 80),
  position integer not null default 1 check (position between 1 and 20),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (product_id, position),
  unique (product_id, name)
);

create table if not exists public.product_variant_values (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.product_variant_groups (id) on delete cascade,
  value text not null check (char_length(btrim(value)) between 1 and 120),
  position integer not null default 1 check (position between 1 and 100),
  created_at timestamptz not null default timezone('utc', now()),
  unique (group_id, position),
  unique (group_id, value)
);

create table if not exists public.product_variants (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products (id) on delete cascade,
  sku text not null check (char_length(btrim(sku)) between 1 and 120),
  option_value_ids uuid[] not null default '{}'::uuid[],
  image_public_id text,
  attributes jsonb not null default '{}'::jsonb check (jsonb_typeof(attributes) = 'object'),
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (product_id, sku)
);

create index if not exists product_variant_groups_product_id_idx on public.product_variant_groups (product_id, position);
create index if not exists product_variant_values_group_id_idx on public.product_variant_values (group_id, position);
create index if not exists product_variants_product_id_idx on public.product_variants (product_id, status);

-- ---------------------------------------------------------------------------
-- Listing content, conditions, price modes, and Class-E configuration
-- ---------------------------------------------------------------------------

alter table public.vendor_listings
  add column if not exists category_id uuid references public.categories (id) on delete restrict,
  add column if not exists description text,
  add column if not exists attributes jsonb not null default '{}'::jsonb,
  add column if not exists pricing_mode text not null default 'fixed',
  add column if not exists price_from_ngwee bigint,
  add column if not exists price_to_ngwee bigint,
  add column if not exists price_per_base_unit_microngwee bigint,
  add column if not exists currency_code char(3) not null default 'ZMW',
  add column if not exists condition_detail text not null default 'new',
  add column if not exists serial_number text,
  add column if not exists imei text,
  add column if not exists vin text,
  add column if not exists mileage_km integer;

update public.vendor_listings
set condition_detail = case condition
  when 'refurbished' then 'refurbished'
  when 'used' then 'used_good'
  else 'new'
end
where condition_detail = 'new' and condition <> 'new';

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_attributes_object_check') then
    alter table public.vendor_listings add constraint vendor_listings_attributes_object_check
      check (jsonb_typeof(attributes) = 'object');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_pricing_mode_check') then
    alter table public.vendor_listings add constraint vendor_listings_pricing_mode_check
      check (pricing_mode in ('fixed', 'measured', 'bundle', 'tiered', 'range', 'from', 'quote_only'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_pricing_values_check') then
    alter table public.vendor_listings add constraint vendor_listings_pricing_values_check
      check (
        (pricing_mode in ('fixed', 'measured', 'bundle', 'tiered') and price_ngwee > 0 and price_from_ngwee is null and price_to_ngwee is null)
        or (pricing_mode = 'from' and price_from_ngwee > 0 and price_to_ngwee is null)
        or (pricing_mode = 'range' and price_from_ngwee > 0 and price_to_ngwee >= price_from_ngwee)
        -- quote-only uses the existing positive price column as a non-public
        -- accounting anchor. The API never exposes or purchases that anchor.
        or (pricing_mode = 'quote_only' and price_ngwee > 0)
      ) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_price_per_base_unit_check') then
    alter table public.vendor_listings add constraint vendor_listings_price_per_base_unit_check
      check (price_per_base_unit_microngwee is null or price_per_base_unit_microngwee > 0);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_condition_detail_check') then
    alter table public.vendor_listings add constraint vendor_listings_condition_detail_check
      check (condition_detail in ('new', 'open_box', 'refurbished', 'used_excellent', 'used_good', 'used_fair', 'parts_not_working'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_condition_detail_parent_check') then
    alter table public.vendor_listings add constraint vendor_listings_condition_detail_parent_check
      check (
        (condition = 'new' and condition_detail in ('new', 'open_box'))
        or (condition = 'refurbished' and condition_detail = 'refurbished')
        or (condition = 'used' and condition_detail in ('used_excellent', 'used_good', 'used_fair', 'parts_not_working'))
      );
  end if;
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_identity_evidence_check') then
    alter table public.vendor_listings add constraint vendor_listings_identity_evidence_check
      check (mileage_km is null or mileage_km >= 0);
  end if;
end
$$;

create index if not exists vendor_listings_category_id_active_idx
  on public.vendor_listings (category_id, status) where status = 'active';
create index if not exists vendor_listings_pricing_mode_idx
  on public.vendor_listings (pricing_mode, status);

create table if not exists public.vendor_listing_variants (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  product_variant_id uuid not null references public.product_variants (id) on delete restrict,
  sku_override text,
  price_ngwee bigint not null check (price_ngwee > 0),
  compare_at_ngwee bigint check (compare_at_ngwee is null or compare_at_ngwee > price_ngwee),
  stock_qty integer check (stock_qty is null or stock_qty >= 0),
  image_public_id text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (listing_id, product_variant_id)
);

create table if not exists public.listing_option_groups (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 80),
  required boolean not null default false,
  position integer not null default 1 check (position between 1 and 30),
  created_at timestamptz not null default timezone('utc', now()),
  unique (listing_id, position),
  unique (listing_id, name)
);

create table if not exists public.listing_option_values (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.listing_option_groups (id) on delete cascade,
  label text not null check (char_length(btrim(label)) between 1 and 120),
  price_delta_ngwee bigint not null default 0,
  deterministic boolean not null default true,
  position integer not null default 1 check (position between 1 and 100),
  created_at timestamptz not null default timezone('utc', now()),
  unique (group_id, position),
  unique (group_id, label)
);

create table if not exists public.listing_specification_snapshots (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete restrict,
  customer_id uuid not null references auth.users (id) on delete restrict,
  selected_option_value_ids uuid[] not null default '{}'::uuid[],
  specification jsonb not null default '{}'::jsonb check (jsonb_typeof(specification) = 'object'),
  reference_public_ids text[] not null default '{}'::text[],
  deterministic_price_ngwee bigint check (deterministic_price_ngwee is null or deterministic_price_ngwee > 0),
  status text not null default 'draft' check (status in ('draft', 'submitted', 'quoted', 'accepted', 'expired', 'cancelled')),
  created_at timestamptz not null default timezone('utc', now()),
  expires_at timestamptz
);

create index if not exists vendor_listing_variants_listing_id_idx on public.vendor_listing_variants (listing_id);
create index if not exists listing_option_groups_listing_id_idx on public.listing_option_groups (listing_id, position);
create index if not exists listing_option_values_group_id_idx on public.listing_option_values (group_id, position);
create index if not exists listing_specification_snapshots_customer_idx on public.listing_specification_snapshots (customer_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Evidence, category policy and the locked launch gates
-- ---------------------------------------------------------------------------

create table if not exists public.category_product_policies (
  category_id uuid primary key references public.categories (id) on delete cascade,
  phase integer not null check (phase between 1 and 3),
  enabled boolean not null default false,
  allowed_product_classes char(1)[] not null default array['A', 'B']::char(1)[]
    check (allowed_product_classes <@ array['A', 'B', 'C', 'D', 'E']::char(1)[]),
  minimum_kyc_tier integer check (minimum_kyc_tier in (1, 2, 3)),
  required_licence_types text[] not null default '{}'::text[],
  evidence_requirements jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence_requirements) = 'object'),
  high_risk boolean not null default false,
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.listing_evidence (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  evidence_type text not null check (evidence_type in ('photo', 'serial', 'imei', 'vin', 'mileage', 'licence', 'purchase_proof', 'authenticity', 'condition_report')),
  storage_key text not null check (char_length(btrim(storage_key)) between 1 and 1024),
  visibility text not null default 'admin_private' check (visibility in ('vendor_private', 'admin_private')),
  verification_status text not null default 'pending' check (verification_status in ('pending', 'verified', 'rejected')),
  reviewer_id uuid references auth.users (id) on delete set null,
  reviewer_note text,
  created_at timestamptz not null default timezone('utc', now()),
  reviewed_at timestamptz
);

create index if not exists listing_evidence_listing_id_idx on public.listing_evidence (listing_id, verification_status);
create index if not exists category_product_policies_phase_idx on public.category_product_policies (phase, enabled);

insert into public.feature_flags (flag, enabled, description) values
  ('product_class_c_customer_release', false, 'Phase-2 commodity catalogue/customer release'),
  ('product_class_d_customer_release', false, 'Used-goods release: evidence, 72-hour escrow and operations approval required'),
  ('product_class_e_customer_release', false, 'Phase-3 made-to-order customer release'),
  ('product_class_d_operations_approved', false, 'Operations checklist approval for used-goods escrow and moderation')
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  ('product_class_d_escrow_hours', '72'::jsonb, 'Used-goods (Class D) escrow hold in hours; release is prohibited until the Class-D gate is enabled'),
  ('fx_rate_max_age_hours', '24'::jsonb, 'Maximum age for an active USD/ZMW rate used at checkout')
on conflict (key) do nothing;

create or replace function public.product_class_customer_released(p_class char(1))
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case p_class
    when 'D' then exists (select 1 from public.feature_flags where flag = 'product_class_d_customer_release' and enabled)
      and exists (select 1 from public.feature_flags where flag = 'product_class_d_operations_approved' and enabled)
    when 'C' then exists (select 1 from public.feature_flags where flag = 'product_class_c_customer_release' and enabled)
    when 'E' then exists (select 1 from public.feature_flags where flag = 'product_class_e_customer_release' and enabled)
    else true
  end;
$$;

revoke execute on function public.product_class_customer_released(char) from public;
grant execute on function public.product_class_customer_released(char) to anon, authenticated, service_role;

create or replace function public.enforce_product_strategy_listing_policy()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  effective_category uuid;
  policy public.category_product_policies%rowtype;
  vendor_tier integer;
begin
  if new.product_id is not null then
    select category_id into effective_category from public.products where id = new.product_id;
  else
    effective_category := new.category_id;
  end if;

  if new.product_class in ('A', 'B', 'C') and new.product_id is null then
    raise exception 'Class % listings require a canonical product', new.product_class using errcode = 'check_violation';
  end if;
  if new.product_class in ('D', 'E') and (new.category_id is null or new.product_id is not null) then
    raise exception 'Class % listings require a standalone category and no canonical product', new.product_class using errcode = 'check_violation';
  end if;
  if new.product_class in ('D', 'E') and char_length(coalesce(btrim(new.description), '')) < 20 then
    raise exception 'Class % listings require a listing-owned description', new.product_class using errcode = 'check_violation';
  end if;

  if new.status <> 'active' then
    return new;
  end if;

  if new.product_class in ('C', 'D', 'E') and not public.product_class_customer_released(new.product_class) then
    raise exception 'product class % is not customer-released', new.product_class using errcode = 'check_violation';
  end if;

  if effective_category is null then
    raise exception 'active listing requires a category' using errcode = 'check_violation';
  end if;
  select * into policy from public.category_product_policies where category_id = effective_category;
  if found then
    if not policy.enabled or not (new.product_class = any(policy.allowed_product_classes)) then
      raise exception 'category policy does not allow active Class % listings', new.product_class using errcode = 'check_violation';
    end if;
    if policy.minimum_kyc_tier is not null then
      select kyc_tier into vendor_tier from public.vendors where id = new.vendor_id;
      if coalesce(vendor_tier, 0) < policy.minimum_kyc_tier then
        raise exception 'vendor KYC tier is below the category policy minimum' using errcode = 'check_violation';
      end if;
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists vendor_listings_product_strategy_policy on public.vendor_listings;
create trigger vendor_listings_product_strategy_policy
  before insert or update of product_id, category_id, product_class, description, status, condition_detail
  on public.vendor_listings
  for each row execute function public.enforce_product_strategy_listing_policy();

-- Public PostgREST reads obey the same Class-D gate as the API. Service-role
-- backend reads remain possible for moderation and pre-release operations.
drop policy if exists vendor_listings_public_active_select on public.vendor_listings;
create policy vendor_listings_public_active_select
  on public.vendor_listings for select
  using (
    status = 'active'
    and public.product_class_customer_released(product_class)
    and exists (
      select 1 from public.vendors v where v.id = vendor_listings.vendor_id and v.status = 'active'
    )
  );

-- ---------------------------------------------------------------------------
-- FX auditability and immutable order snapshots
-- ---------------------------------------------------------------------------

create table if not exists public.fx_rates (
  id uuid primary key default gen_random_uuid(),
  base_currency char(3) not null default 'USD' check (base_currency = 'USD'),
  quote_currency char(3) not null default 'ZMW' check (quote_currency = 'ZMW'),
  rate_zmw_per_usd_micros bigint not null check (rate_zmw_per_usd_micros > 0),
  vendor_margin_bps integer not null default 0 check (vendor_margin_bps between 0 and 5000),
  source text not null check (char_length(btrim(source)) between 1 and 160),
  source_reference text,
  effective_at timestamptz not null,
  expires_at timestamptz not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  superseded_at timestamptz,
  check (expires_at > effective_at)
);

create unique index if not exists fx_rates_one_current_rate
  on public.fx_rates (base_currency, quote_currency)
  where superseded_at is null;
create index if not exists fx_rates_active_window_idx on public.fx_rates (effective_at desc, expires_at);

alter table public.orders
  add column if not exists fx_snapshot jsonb not null default '{}'::jsonb;
alter table public.order_items
  add column if not exists product_snapshot jsonb not null default '{}'::jsonb;
alter table public.order_item_products
  add column if not exists listing_snapshot jsonb not null default '{}'::jsonb,
  add column if not exists specification_snapshot_id uuid references public.listing_specification_snapshots (id) on delete set null;

create or replace function public.guard_orders_fx_snapshot_immutable()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.fx_snapshot is not distinct from old.fx_snapshot then
    return new;
  end if;
  if current_user in ('postgres', 'supabase_admin') then
    return new;
  end if;
  raise exception 'orders.fx_snapshot is immutable after creation (order %)', old.id using errcode = 'check_violation';
end;
$$;

revoke execute on function public.guard_orders_fx_snapshot_immutable() from public, anon, authenticated;
drop trigger if exists orders_fx_snapshot_immutable on public.orders;
create trigger orders_fx_snapshot_immutable
  before update of fx_snapshot on public.orders
  for each row execute function public.guard_orders_fx_snapshot_immutable();

-- ---------------------------------------------------------------------------
-- RLS for new strategy tables. Public rows are active canonical/variant data;
-- private evidence and specifications never inherit public listing visibility.
-- ---------------------------------------------------------------------------

alter table public.product_variant_groups enable row level security;
alter table public.product_variant_values enable row level security;
alter table public.product_variants enable row level security;
alter table public.vendor_listing_variants enable row level security;
alter table public.listing_option_groups enable row level security;
alter table public.listing_option_values enable row level security;
alter table public.listing_specification_snapshots enable row level security;
alter table public.category_product_policies enable row level security;
alter table public.listing_evidence enable row level security;
alter table public.fx_rates enable row level security;

alter table public.product_variant_groups force row level security;
alter table public.product_variant_values force row level security;
alter table public.product_variants force row level security;
alter table public.vendor_listing_variants force row level security;
alter table public.listing_option_groups force row level security;
alter table public.listing_option_values force row level security;
alter table public.listing_specification_snapshots force row level security;
alter table public.category_product_policies force row level security;
alter table public.listing_evidence force row level security;
alter table public.fx_rates force row level security;

create policy product_variant_groups_public_select on public.product_variant_groups for select using (
  exists (select 1 from public.products p where p.id = product_variant_groups.product_id and p.status = 'active')
);
create policy product_variant_values_public_select on public.product_variant_values for select using (
  exists (select 1 from public.product_variant_groups g join public.products p on p.id = g.product_id where g.id = product_variant_values.group_id and p.status = 'active')
);
create policy product_variants_public_select on public.product_variants for select using (
  status = 'active' and exists (select 1 from public.products p where p.id = product_variants.product_id and p.status = 'active')
);
create policy vendor_listing_variants_public_select on public.vendor_listing_variants for select using (
  exists (select 1 from public.vendor_listings l where l.id = vendor_listing_variants.listing_id and l.status = 'active' and public.product_class_customer_released(l.product_class))
);
create policy listing_option_groups_public_select on public.listing_option_groups for select using (
  exists (select 1 from public.vendor_listings l where l.id = listing_option_groups.listing_id and l.status = 'active' and l.product_class = 'E' and public.product_class_customer_released(l.product_class))
);
create policy listing_option_values_public_select on public.listing_option_values for select using (
  exists (select 1 from public.listing_option_groups g join public.vendor_listings l on l.id = g.listing_id where g.id = listing_option_values.group_id and l.status = 'active' and l.product_class = 'E' and public.product_class_customer_released(l.product_class))
);
create policy category_product_policies_public_select on public.category_product_policies for select using (true);
create policy fx_rates_public_current_select on public.fx_rates for select using (superseded_at is null and effective_at <= now() and expires_at > now());

create policy listing_specification_snapshots_customer_select on public.listing_specification_snapshots for select to authenticated using (customer_id = (select auth.uid()));
create policy listing_evidence_owner_select on public.listing_evidence for select to authenticated using (
  exists (select 1 from public.vendor_listings l join public.vendors v on v.id = l.vendor_id where l.id = listing_evidence.listing_id and v.owner_user_id = (select auth.uid()))
);
create policy listing_evidence_admin_all on public.listing_evidence for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));

-- All editing paths stay server/admin mediated until their app contracts land.
create policy category_product_policies_admin_all on public.category_product_policies for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy fx_rates_admin_all on public.fx_rates for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));

create policy product_variant_groups_admin_all on public.product_variant_groups for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy product_variant_values_admin_all on public.product_variant_values for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy product_variants_admin_all on public.product_variants for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy vendor_listing_variants_admin_all on public.vendor_listing_variants for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy listing_option_groups_admin_all on public.listing_option_groups for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy listing_option_values_admin_all on public.listing_option_values for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));
create policy listing_specification_snapshots_admin_all on public.listing_specification_snapshots for all to authenticated using (public.has_role('admin')) with check (public.has_role('admin'));

grant select on public.product_variant_groups, public.product_variant_values, public.product_variants,
  public.vendor_listing_variants, public.listing_option_groups, public.listing_option_values,
  public.category_product_policies, public.fx_rates to anon, authenticated;
grant select on public.listing_specification_snapshots, public.listing_evidence to authenticated;

comment on table public.listing_evidence is
  'Private evidence for used/high-risk listings. Customer delivery is deliberately forbidden; only the owner and authorised administrators may read it.';
comment on table public.fx_rates is
  'Audited USD/ZMW rates in integer micro-ZMW per USD. Checkout snapshots the selected rate and margin; it never recalculates an already-placed order.';
