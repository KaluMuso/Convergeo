-- Service packages: from fixed Basic/Standard/Premium tiers to an open, ordered list.
--
-- Founder decision (2026-11-27): a service may offer up to 10 packages, each with a
-- vendor-chosen name, price, description, delivery time and features, in a vendor
-- chosen order. Additive and backward compatible:
--   * `tier` stays as an OPTIONAL legacy label (nullable); existing rows keep their
--     tier, and their `name` is already vendor-chosen so nothing is lost;
--   * the one-per-tier unique key is dropped (replaced by a non-unique lookup index);
--   * new `sort_order` column, backfilled from the old tier order
--     (basic 0, standard 1, premium 2), so existing services render unchanged;
--   * a database-level cap of 10 ACTIVE packages per service (the API also checks it
--     and returns the `package_limit_reached` error code).
-- No money object is touched: `price_ngwee` is still integer ngwee (NULL = quote),
-- and `rfq_threads.package_snapshot` is unchanged.
--
-- Down (reversible; run manually, only valid while every service still has at most one
-- row per tier, so first delete or relabel extras):
--   drop trigger if exists service_packages_cap_guard_trg on public.service_packages;
--   drop function if exists public.service_packages_cap_guard();
--   drop index if exists public.service_packages_service_order_idx;
--   -- every row needs a distinct tier per service before the old key can return:
--   delete from public.service_packages where tier is null;   -- or relabel by hand
--   alter table public.service_packages drop constraint service_packages_tier_check;
--   alter table public.service_packages
--     add constraint service_packages_tier_check
--       check (tier in ('basic', 'standard', 'premium'));
--   alter table public.service_packages alter column tier set not null;
--   alter table public.service_packages
--     add constraint service_packages_one_per_tier unique (service_id, tier);
--   alter table public.service_packages drop column if exists sort_order;

alter table public.service_packages
  add column if not exists sort_order integer not null default 0
    check (sort_order between 0 and 1000);

-- Keep the old tier order for existing rows.
update public.service_packages
   set sort_order = case tier
         when 'basic' then 0
         when 'standard' then 1
         when 'premium' then 2
         else sort_order
       end
 where tier is not null;

-- tier becomes an optional label.
alter table public.service_packages drop constraint if exists service_packages_one_per_tier;
alter table public.service_packages alter column tier drop not null;
alter table public.service_packages drop constraint if exists service_packages_tier_check;
alter table public.service_packages
  add constraint service_packages_tier_check
    check (tier is null or tier in ('basic', 'standard', 'premium'));

create index if not exists service_packages_service_order_idx
  on public.service_packages (service_id, sort_order, created_at);

comment on table public.service_packages is
  'Up to 10 active packages per service, vendor-ordered (sort_order). tier is an optional legacy label. price_ngwee NULL = request a quote. Written only by the API (vendor-owned, audited status transitions); public read for active packages of active services of active vendors.';
comment on column public.service_packages.sort_order is
  'Vendor-chosen display order within a service (ascending); ties break on created_at.';

-- At most 10 ACTIVE packages per service. Serialised per service so two concurrent
-- inserts cannot both slip under the cap.
create or replace function public.service_packages_cap_guard()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  active_count integer;
begin
  if new.status <> 'active' then
    return new;
  end if;
  if tg_op = 'UPDATE' and old.status = 'active' and old.service_id = new.service_id then
    return new;
  end if;
  perform pg_advisory_xact_lock(hashtextextended(new.service_id::text, 0));
  select count(*) into active_count
    from public.service_packages
   where service_id = new.service_id
     and status = 'active'
     and id <> new.id;
  if active_count >= 10 then
    raise exception 'service_packages: a service can have at most 10 active packages'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

revoke all on function public.service_packages_cap_guard() from public;
revoke execute on function public.service_packages_cap_guard() from anon, authenticated;

drop trigger if exists service_packages_cap_guard_trg on public.service_packages;
create trigger service_packages_cap_guard_trg
  before insert or update of status, service_id on public.service_packages
  for each row execute function public.service_packages_cap_guard();
