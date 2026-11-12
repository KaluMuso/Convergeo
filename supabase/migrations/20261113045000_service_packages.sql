-- Service packages — Basic / Standard / Premium tiers on a service listing.
--
-- Design: docs/plan/service-packages.md. Additive only:
--   * new table public.service_packages (FORCE RLS, no client write grants);
--   * two nullable columns on public.rfq_threads (package_id, package_snapshot) so a
--     quote request can carry the package the customer picked.
-- No payment, order or ledger object is touched: packages route to RFQ only (SP-1).
--
-- Down (reversible):
--   drop trigger if exists rfq_threads_package_guard_trg on public.rfq_threads;
--   drop function if exists public.rfq_threads_package_guard();
--   alter table public.rfq_threads drop column if exists package_snapshot,
--                                  drop column if exists package_id;
--   drop table if exists public.service_packages;   -- cascades its trigger/function use
--   drop function if exists public.service_packages_vendor_guard();

-- ---------------------------------------------------------------------------
-- Table
-- ---------------------------------------------------------------------------
create table public.service_packages (
  id uuid primary key default gen_random_uuid(),
  service_id uuid not null references public.services (id) on delete cascade,
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  tier text not null check (tier in ('basic', 'standard', 'premium')),
  name text not null check (char_length(btrim(name)) between 2 and 40),
  description text check (description is null or char_length(description) <= 300),
  -- Integer ngwee (convention #1). NULL = "request a quote" for this package.
  price_ngwee bigint check (price_ngwee is null or price_ngwee > 0),
  delivery_days integer not null check (delivery_days between 1 and 90),
  -- NULL = revisions do not apply to this kind of service.
  revisions integer check (revisions is null or revisions between 0 and 10),
  includes text[] not null default '{}'
    check (cardinality(includes) <= 8),
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  -- At most one package per tier per service ⇒ at most three per service.
  constraint service_packages_one_per_tier unique (service_id, tier)
);

comment on table public.service_packages is
  'Up to three tiers (basic/standard/premium) per service. price_ngwee NULL = request a quote. Written only by the API (vendor-owned, audited status transitions); public read for active packages of active services of active vendors.';

create index service_packages_vendor_idx on public.service_packages (vendor_id);

create trigger service_packages_set_updated_at
  before update on public.service_packages
  for each row execute function public.set_updated_at();

-- vendor_id is denormalised for RLS; it must always equal the service's vendor.
create or replace function public.service_packages_vendor_guard()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  owner_vendor uuid;
begin
  select vendor_id into owner_vendor from public.services where id = new.service_id;
  if owner_vendor is null then
    raise exception 'service_packages: service % does not exist', new.service_id
      using errcode = 'foreign_key_violation';
  end if;
  if owner_vendor <> new.vendor_id then
    raise exception 'service_packages: vendor % does not own service %',
      new.vendor_id, new.service_id
      using errcode = 'check_violation';
  end if;
  if exists (
    select 1 from unnest(new.includes) as item
     where char_length(btrim(item)) = 0 or char_length(item) > 120
  ) then
    raise exception 'service_packages: include items must be 1-120 characters'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

revoke all on function public.service_packages_vendor_guard() from public;
revoke execute on function public.service_packages_vendor_guard() from anon, authenticated;

create trigger service_packages_vendor_guard_trg
  before insert or update on public.service_packages
  for each row execute function public.service_packages_vendor_guard();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.service_packages enable row level security;
alter table public.service_packages force row level security;

create policy service_packages_public_select
  on public.service_packages
  for select
  using (
    status = 'active'
    and exists (
      select 1
        from public.services s
        join public.vendors v on v.id = s.vendor_id
       where s.id = service_packages.service_id
         and s.status = 'active'
         and v.status = 'active'
    )
  );

create policy service_packages_owner_select
  on public.service_packages
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
       where v.id = service_packages.vendor_id
         and v.owner_user_id = (select auth.uid())
    )
  );

create policy service_packages_admin_select
  on public.service_packages
  for select
  to authenticated
  using (public.has_role('admin'));

revoke all on table public.service_packages from anon, authenticated;
grant select on table public.service_packages to anon, authenticated;
grant select, insert, update, delete on table public.service_packages to service_role;
-- Deliberately no client INSERT/UPDATE/DELETE: validation, moderation and the
-- audited status transitions live in the API (convention #4).

-- ---------------------------------------------------------------------------
-- RFQ threads carry the chosen package
-- ---------------------------------------------------------------------------
alter table public.rfq_threads
  add column if not exists package_id uuid
    references public.service_packages (id) on delete set null,
  add column if not exists package_snapshot jsonb;

comment on column public.rfq_threads.package_id is
  'Service package the customer asked about (service RFQs only). Snapshot in package_snapshot is what the customer saw.';
comment on column public.rfq_threads.package_snapshot is
  'Immutable copy of the package at request time: tier, name, price_ngwee (int or null), delivery_days, revisions, includes.';

create or replace function public.rfq_threads_package_guard()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  pkg_service uuid;
begin
  if new.package_id is null then
    return new;
  end if;
  if new.service_id is null then
    raise exception 'rfq_threads: package % requires a service RFQ', new.package_id
      using errcode = 'check_violation';
  end if;
  select service_id into pkg_service from public.service_packages where id = new.package_id;
  if pkg_service is distinct from new.service_id then
    raise exception 'rfq_threads: package % does not belong to service %',
      new.package_id, new.service_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

revoke all on function public.rfq_threads_package_guard() from public;
revoke execute on function public.rfq_threads_package_guard() from anon, authenticated;

drop trigger if exists rfq_threads_package_guard_trg on public.rfq_threads;
create trigger rfq_threads_package_guard_trg
  before insert or update of package_id, service_id on public.rfq_threads
  for each row execute function public.rfq_threads_package_guard();
