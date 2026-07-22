-- 0069_orders_commission_snapshot_immutable.sql
-- Freeze orders.commission_snapshot after creation (PAY-07 / R-6 — defence-in-depth).
--
-- orders.commission_snapshot (0005_orders.sql) captures the purchase-time per-line
-- commission basis and is the SOLE source of commission at release / payout time
-- (services/api/app/services/escrow/release_accounting.py + release.py). It is written
-- exactly ONCE, on the order INSERT (services/api/app/services/orders/create.py — a
-- plain INSERT, never an upsert), and no code path updates it afterwards; the release
-- engine only READS it and scales an in-memory copy for partial release.
--
-- Silently rewriting it after purchase would change vendor net / platform commission
-- on every subsequent release (skim risk). This BEFORE UPDATE trigger makes the column
-- immutable for every application role — anon / authenticated / service_role / admin —
-- so no app path, compromised key, or direct PostgREST PATCH can alter the commission
-- basis. Only the DB owner / superuser (migrations, dashboard SQL, an audited emergency
-- correction) keeps an escape hatch.
--
-- SECURITY INVOKER is deliberate: the guard tests `current_user`, which reflects the
-- EFFECTIVE caller (the role PostgREST / the RLS harness switches into). A SECURITY
-- DEFINER function would always see the function owner and could never distinguish an
-- app request from a migration. `BEFORE UPDATE OF commission_snapshot` means the trigger
-- never fires for ordinary order updates (status transitions etc.) that do not touch the
-- column, and a no-op write of the same value is allowed. Additive + reversible; no
-- table-shape change (db.ts unaffected — trigger functions are excluded from the types).
--
-- Down (manual):
--   drop trigger orders_commission_snapshot_immutable on public.orders;
--   drop function public.guard_orders_commission_snapshot_immutable();

create or replace function public.guard_orders_commission_snapshot_immutable()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  -- No actual change → nothing to guard (permits no-op writes of the same value).
  if new.commission_snapshot is not distinct from old.commission_snapshot then
    return new;
  end if;

  -- The commission basis changed. Only the DB owner / superuser may do this;
  -- every application role is frozen. current_user is the effective caller under
  -- SECURITY INVOKER (postgres/supabase_admin for migrations & dashboard SQL;
  -- anon/authenticated/service_role for any PostgREST request).
  if current_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  raise exception
    'orders.commission_snapshot is immutable after creation (order %)', old.id
    using errcode = 'check_violation';
end;
$$;

revoke execute on function public.guard_orders_commission_snapshot_immutable()
  from public, anon, authenticated;

create trigger orders_commission_snapshot_immutable
  before update of commission_snapshot on public.orders
  for each row
  execute function public.guard_orders_commission_snapshot_immutable();
