-- Lock vendor payout/tier columns and client-side dispute/return inserts.
--
-- Two confirmed holes (verified live on production, 2026-11-27):
--
-- 1. public.vendors: policy vendors_owner_update + the UPDATE grant let an
--    owner PATCH payout_msisdn, payout_rail, payout_hold_until, commercial_tier,
--    caps_snapshot and owner_user_id straight through PostgREST (redirect their
--    own payouts, clear a payout hold, raise caps, hand the shop to another
--    user). guard_vendor_status_update() (0002, 0057) only blocked status,
--    kyc_tier and preferred_badge. This migration extends it (CREATE OR REPLACE,
--    existing behaviour and exemptions unchanged) so non-exempt callers cannot
--    change those six columns either. Payout changes go through the API with
--    the service-role key (routers/vendor_payouts.py), which stays exempt.
--
-- 2. public.disputes / public.returns: the INSERT policies
--    disputes_opener_insert (WITH CHECK opener_user_id = auth.uid()) and
--    returns_customer_insert plus the INSERT grant let any signed-in user write
--    rows directly. For disputes that meant opening a dispute on ANY order
--    (freezing payouts). The API (services/disputes, services/returns, service
--    role) is the only legitimate writer, so the policies are dropped and
--    INSERT is revoked from anon and authenticated. SELECT/UPDATE policies and
--    service_role grants are untouched.
--
-- Additive-safe and idempotent (IF EXISTS / CREATE OR REPLACE).
--
-- REVERSAL (documented; run manually if ever needed):
--   -- 1. restore the 0057 definition of public.guard_vendor_status_update()
--   --    (re-run the CREATE OR REPLACE FUNCTION block from
--   --    supabase/migrations/0057_vendor_lifecycle_client_guards.sql, section 2).
--   -- 2. re-open client inserts:
--   --   grant insert on table public.disputes to authenticated;
--   --   grant insert on table public.returns to authenticated;
--   --   create policy disputes_opener_insert on public.disputes
--   --     for insert to authenticated
--   --     with check (opener_user_id = (select auth.uid()));
--   --   create policy returns_customer_insert on public.returns
--   --     for insert to authenticated
--   --     with check (exists (
--   --       select 1 from public.order_items oi
--   --       join public.orders o on o.id = oi.order_id
--   --       where oi.id = order_item_id and o.customer_id = (select auth.uid())));

-- ---------------------------------------------------------------------------
-- 1. vendors: owner may not change payout / tier / caps / ownership columns
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

  if new.payout_msisdn is distinct from old.payout_msisdn
    or new.payout_rail is distinct from old.payout_rail
    or new.payout_hold_until is distinct from old.payout_hold_until
    or new.commercial_tier is distinct from old.commercial_tier
    or new.caps_snapshot is distinct from old.caps_snapshot
    or new.owner_user_id is distinct from old.owner_user_id then
    raise exception 'vendor payout, commercial_tier, caps_snapshot, and owner columns are server-controlled';
  end if;

  return new;
end;
$$;

comment on function public.guard_vendor_status_update() is
  'Owners must not mutate vendor lifecycle/trust/payout/tier/caps/owner fields via PostgREST; admins/service bypass.';

-- ---------------------------------------------------------------------------
-- 2. disputes / returns: service-role API is the only writer
-- ---------------------------------------------------------------------------

drop policy if exists disputes_opener_insert on public.disputes;
drop policy if exists returns_customer_insert on public.returns;

revoke insert on table public.disputes from anon, authenticated;
revoke insert on table public.returns from anon, authenticated;
