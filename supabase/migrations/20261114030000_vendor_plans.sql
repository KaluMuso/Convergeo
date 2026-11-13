-- Vendor listing plans (post-pilot capacity work, founder-approved 2026-11-13).
--
-- Additive and reversible. Extends the existing quota stack instead of
-- duplicating it:
--   * `vendor_quotas` (0008) stays the KYC-tier TRUST cap (T1 = 30 listings).
--   * `vendor_plans` (new) is the COMMERCIAL cap: what a vendor's plan allows.
--   * The effective listing cap is least(KYC cap, plan cap). An unverified T1
--     vendor therefore never buys their way past the trust cap.
--   * `feature_flags.paid_tiers` (0008) keeps meaning "subscription billing";
--     it stays off. This migration adds `vendor_plans` (caps + assignment only).
--   * `vendors.commercial_tier` (0070) stays the directory display badge and is
--     not read here (its bronze..platinum check cannot carry admin-defined plans).
--
-- Plans are priced by features, not by SKU count: the limit counts distinct
-- listings in draft/active/paused. Stock quantity and variants never count.
-- Over the limit, nothing is deleted or paused: only new admissions are refused.
-- Billing is out of scope; `vendor_plan_assignments` carries an inert seam
-- (billing_status / paid_through / billing_reference) for a future Lenco charge.
--
-- Reversal (no data outside these objects depends on them):
--   drop trigger vendor_listing_admission_guard on public.vendor_listings;
--   recreate guard_vendor_listing_admission() from 20261001120000 and its trigger;
--   drop function public.vendor_plan_listing_cap(uuid);
--   drop table public.vendor_plan_overrides, public.vendor_plan_assignments,
--     public.vendor_plans;
--   delete from public.feature_flags where flag = 'vendor_plans';
begin;

insert into public.feature_flags (flag, enabled, description) values
  ('vendor_plans', false,
   'Vendor listing plans: plan caps on listings/photos + upgrade prompts (no billing)')
on conflict (flag) do nothing;

-- ---------------------------------------------------------------------------
-- vendor_plans — admin-editable catalogue of plans
-- ---------------------------------------------------------------------------
create table public.vendor_plans (
  key text primary key check (key ~ '^[a-z][a-z0-9_]{1,31}$'),
  name text not null check (char_length(btrim(name)) between 1 and 60),
  -- Monthly price, integer ngwee (K49 = 4900). Display only until billing ships.
  price_ngwee bigint not null default 0
    check (price_ngwee between 0 and 100000000),
  -- NULL = unlimited listings.
  max_listings integer check (max_listings is null or max_listings between 0 and 1000000),
  -- Own photos a vendor may upload per listing; never above the hard ≤8 rule.
  max_images_per_listing integer not null default 8
    check (max_images_per_listing between 1 and 8),
  featured_slots integer not null default 0 check (featured_slots between 0 and 100),
  analytics_depth text not null default 'basic'
    check (analytics_depth in ('basic', 'standard', 'advanced')),
  wholesale_tools boolean not null default false,
  is_default boolean not null default false,
  active boolean not null default true,
  position integer not null default 0 check (position between 0 and 1000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_plans_default_is_active check (not is_default or active)
);

comment on table public.vendor_plans is
  'Commercial vendor plans (admin-editable). Listing cap = least(KYC cap, plan cap). Stock never counts.';
comment on column public.vendor_plans.max_listings is 'NULL means unlimited listings.';

create unique index vendor_plans_single_default_idx
  on public.vendor_plans (is_default) where is_default;

create trigger vendor_plans_set_updated_at
  before update on public.vendor_plans
  for each row execute function public.set_updated_at();

create trigger vendor_plans_audit
  after insert or update or delete on public.vendor_plans
  for each row execute function public.audit_config_change();

-- Proposed defaults (founder 2026-11-13). Prices in ngwee.
insert into public.vendor_plans
  (key, name, price_ngwee, max_listings, max_images_per_listing, featured_slots,
   analytics_depth, wholesale_tools, is_default, position)
values
  ('free', 'Free', 0, 25, 8, 0, 'basic', false, true, 0),
  ('starter', 'Starter', 4900, 150, 8, 1, 'standard', false, false, 1),
  ('business', 'Business', 14900, 1000, 8, 3, 'advanced', true, false, 2),
  ('pro', 'Pro', 34900, null, 8, 10, 'advanced', true, false, 3);

-- ---------------------------------------------------------------------------
-- vendor_plan_assignments — one current plan per vendor (record only)
-- ---------------------------------------------------------------------------
create table public.vendor_plan_assignments (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null unique references public.vendors (id) on delete cascade,
  plan_key text not null references public.vendor_plans (key) on delete restrict,
  source text not null default 'admin' check (source in ('admin', 'subscription')),
  -- Billing seam (inert until a Lenco subscription charge exists).
  billing_status text not null default 'not_billed'
    check (billing_status in ('not_billed', 'active', 'past_due', 'lapsed')),
  paid_through date,
  billing_reference text
    check (billing_reference is null or billing_reference ~ '^[-._A-Za-z0-9]{1,64}$'),
  note text check (note is null or char_length(note) <= 500),
  assigned_by uuid,
  assigned_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index vendor_plan_assignments_plan_key_idx
  on public.vendor_plan_assignments (plan_key);

create trigger vendor_plan_assignments_set_updated_at
  before update on public.vendor_plan_assignments
  for each row execute function public.set_updated_at();

create trigger vendor_plan_assignments_audit
  after insert or update or delete on public.vendor_plan_assignments
  for each row execute function public.audit_config_change();

-- ---------------------------------------------------------------------------
-- vendor_plan_overrides — per-vendor exception with a mandatory expiry
-- ---------------------------------------------------------------------------
create table public.vendor_plan_overrides (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null unique references public.vendors (id) on delete cascade,
  max_listings integer check (max_listings is null or max_listings between 0 and 1000000),
  unlimited_listings boolean not null default false,
  max_images_per_listing integer
    check (max_images_per_listing is null or max_images_per_listing between 1 and 8),
  expires_at timestamptz not null,
  reason text not null check (char_length(btrim(reason)) between 1 and 500),
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_plan_overrides_listing_shape
    check (not (unlimited_listings and max_listings is not null)),
  constraint vendor_plan_overrides_not_empty
    check (unlimited_listings or max_listings is not null or max_images_per_listing is not null)
);

create index vendor_plan_overrides_expires_at_idx
  on public.vendor_plan_overrides (expires_at);

create trigger vendor_plan_overrides_set_updated_at
  before update on public.vendor_plan_overrides
  for each row execute function public.set_updated_at();

create trigger vendor_plan_overrides_audit
  after insert or update or delete on public.vendor_plan_overrides
  for each row execute function public.audit_config_change();

-- ---------------------------------------------------------------------------
-- Row level security. Writes are API-only (service role + admin audit_log);
-- clients may only read: plans (active, or all for admins), and their OWN
-- assignment/override. Another vendor's plan, price deal or override is never
-- visible to a vendor.
-- ---------------------------------------------------------------------------
alter table public.vendor_plans enable row level security;
alter table public.vendor_plan_assignments enable row level security;
alter table public.vendor_plan_overrides enable row level security;

revoke all on public.vendor_plans from public, anon, authenticated;
revoke all on public.vendor_plan_assignments from public, anon, authenticated;
revoke all on public.vendor_plan_overrides from public, anon, authenticated;
grant select on public.vendor_plans to authenticated;
grant select on public.vendor_plan_assignments to authenticated;
grant select on public.vendor_plan_overrides to authenticated;
grant all on public.vendor_plans to service_role;
grant all on public.vendor_plan_assignments to service_role;
grant all on public.vendor_plan_overrides to service_role;

create policy vendor_plans_select
  on public.vendor_plans
  for select
  to authenticated
  using (active or public.has_role('admin'));

create policy vendor_plan_assignments_select_own
  on public.vendor_plan_assignments
  for select
  to authenticated
  using (
    public.has_role('admin')
    or exists (
      select 1 from public.vendors v
      where v.id = vendor_plan_assignments.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy vendor_plan_overrides_select_own
  on public.vendor_plan_overrides
  for select
  to authenticated
  using (
    public.has_role('admin')
    or exists (
      select 1 from public.vendors v
      where v.id = vendor_plan_overrides.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- Plan listing cap resolver. NULL = no plan cap (flag off, unlimited plan or
-- override, or no default plan configured — the KYC cap still applies).
-- Same rule as app/services/vendor_plans/resolver.py.
-- ---------------------------------------------------------------------------
create function public.vendor_plan_listing_cap(p_vendor_id uuid) returns integer
language plpgsql stable security definer set search_path = pg_catalog, public
as $$
declare
  v_enabled boolean;
  v_unlimited boolean;
  v_cap integer;
begin
  select ff.enabled into v_enabled from public.feature_flags ff where ff.flag = 'vendor_plans';
  if not coalesce(v_enabled, false) then
    return null;
  end if;

  select o.unlimited_listings, o.max_listings into v_unlimited, v_cap
    from public.vendor_plan_overrides o
    where o.vendor_id = p_vendor_id and o.expires_at > now();
  if found then
    if v_unlimited then
      return null;
    end if;
    if v_cap is not null then
      return v_cap;
    end if;
  end if;

  select p.max_listings into v_cap
    from public.vendor_plan_assignments a
    join public.vendor_plans p on p.key = a.plan_key
    where a.vendor_id = p_vendor_id;
  if found then
    return v_cap;
  end if;

  select p.max_listings into v_cap from public.vendor_plans p where p.is_default;
  return v_cap;
end;
$$;

revoke all on function public.vendor_plan_listing_cap(uuid) from public, anon, authenticated;
grant execute on function public.vendor_plan_listing_cap(uuid) to service_role;

-- ---------------------------------------------------------------------------
-- Listing admission guard: least(KYC cap, plan cap). Body otherwise identical
-- to 20261001120000 (same advisory lock, same counted statuses, same error),
-- so the API/import/intake error handling keeps working unchanged.
-- ---------------------------------------------------------------------------
create or replace function public.guard_vendor_listing_admission() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_tier integer;
  v_max integer;
  v_plan_cap integer;
  v_count bigint;
begin
  if new.status not in ('draft', 'active', 'paused') then return new; end if;
  if tg_op = 'UPDATE' then
    if old.vendor_id = new.vendor_id and old.status in ('draft', 'active', 'paused') then
      return new;
    end if;
  end if;
  if current_setting('transaction_isolation') <> 'read committed' then
    raise sqlstate '40001' using message = 'listing_admission_requires_read_committed';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('listing-admission:' || new.vendor_id::text, 0));
  select coalesce(max(tier), 1) into v_tier from public.kyc_records
    where vendor_id = new.vendor_id and status = 'approved';
  select max_listings into v_max from public.vendor_quotas where tier = v_tier;
  if v_max is null then
    raise sqlstate 'PT500' using message = 'listing_quota_missing';
  end if;
  v_plan_cap := public.vendor_plan_listing_cap(new.vendor_id);
  if v_plan_cap is not null then
    v_max := least(v_max, v_plan_cap);
  end if;
  -- Distinct listings only: stock_qty and variants never count.
  select count(*) into v_count from public.vendor_listings
    where vendor_id = new.vendor_id and status in ('draft', 'active', 'paused')
      and id <> new.id;
  if v_count >= v_max then
    raise sqlstate 'PT403' using message = 'listing_cap_exceeded';
  end if;
  return new;
end;
$$;

revoke all on function public.guard_vendor_listing_admission() from public, anon, authenticated;

commit;
