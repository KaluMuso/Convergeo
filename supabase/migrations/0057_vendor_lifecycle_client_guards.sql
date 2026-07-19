-- 0057: Block client self-activation / trust-signal writes on vendors.
--
-- Gap (0002): `guard_vendor_status_update` runs BEFORE UPDATE only, and does not
-- cover `preferred_badge`. `vendors_owner_insert` only checks ownership, so an
-- authenticated client can INSERT status=active + kyc_tier + preferred_badge and
-- appear as a public/verified storefront without KYC.
--
-- Additive: INSERT guard + tighten UPDATE guard. Privileged paths
-- (service_role / admin / superuser) unchanged.
-- Reversible: drop the insert trigger/function; restore prior UPDATE function body.

-- ---------------------------------------------------------------------------
-- 1. INSERT: owners may only create draft, unverified rows
-- ---------------------------------------------------------------------------

create or replace function public.guard_vendor_lifecycle_insert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from 'draft' then
    raise exception 'vendor status is server-controlled';
  end if;

  if new.kyc_tier is not null then
    raise exception 'vendor kyc_tier is server-controlled';
  end if;

  if coalesce(new.preferred_badge, false) then
    raise exception 'vendor preferred_badge is server-controlled';
  end if;

  return new;
end;
$$;

drop trigger if exists vendors_guard_lifecycle_insert on public.vendors;
create trigger vendors_guard_lifecycle_insert
  before insert on public.vendors
  for each row
  execute function public.guard_vendor_lifecycle_insert();

comment on function public.guard_vendor_lifecycle_insert() is
  'Owners may INSERT only draft vendors without kyc_tier/preferred_badge; admin/service bypass.';

revoke all on function public.guard_vendor_lifecycle_insert() from public;
revoke execute on function public.guard_vendor_lifecycle_insert() from public, anon, authenticated;
grant execute on function public.guard_vendor_lifecycle_insert() to postgres, service_role;

-- ---------------------------------------------------------------------------
-- 2. UPDATE: also lock preferred_badge (was owner-writable)
-- ---------------------------------------------------------------------------

create or replace function public.guard_vendor_status_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from old.status
    or new.kyc_tier is distinct from old.kyc_tier
    or new.preferred_badge is distinct from old.preferred_badge then
    raise exception 'vendor status, kyc_tier, and preferred_badge are server-controlled';
  end if;

  return new;
end;
$$;

comment on function public.guard_vendor_status_update() is
  'Owners must not mutate vendor lifecycle/trust fields via PostgREST; admins/service bypass.';
