-- Event ticket integrity (fix/event-ticket-integrity).
--
-- 1. Unpublished events keep sold tickets valid (founder policy).
--    Admin unpublish / moderation hold moves an event back to 'draft'. Until now
--    require_published_event_for_issued_ticket() rejected every write that left a
--    ticket 'issued' on a non-published event, so on an unpublished event:
--      * a paid order whose tickets were not yet issued could never be issued
--        (the buyer paid and had no ticket), and
--      * existing issued tickets could not be transferred or re-keyed.
--    The guard now admits, on a 'draft' event only:
--      * UPDATEs of an already-issued credential (transfer, holder name, linking
--        a claimed hold to its paid order item), and
--      * INSERTs of PAID credentials (order_item_id set — server issuance only;
--        clients can never insert tickets, see the role check below).
--    New unpaid claims (order_item_id NULL) still require 'published', so sales
--    stop while the event is unpublished. 'cancelled' and 'completed' still
--    reject issued credentials; cancellation voids tickets in the same
--    transaction (cancel_active_tickets_for_event, unchanged).
--
-- 2. Promo-code usage limit enforced atomically.
--    The purchase path counted event_promo_redemptions and inserted separately,
--    so concurrent checkouts could all pass the count and exceed
--    max_redemptions. A BEFORE INSERT trigger now locks the promo row
--    (FOR UPDATE) and re-counts under that lock; each plpgsql statement takes a
--    fresh READ COMMITTED snapshot, so a waiter sees the redemption committed by
--    the lock holder. Over the limit raises SQLSTATE 23514 with message
--    'event_promo_redemption_limit_reached' (mapped to promo_exhausted by the
--    API). A replay for an order that already redeemed passes through so the
--    caller's ON CONFLICT (order_id) DO NOTHING stays a no-op.
--
-- Additive only (function body replaced in place, new trigger + function).
--
-- Reversible rollback:
--   DROP TRIGGER IF EXISTS event_promo_redemptions_enforce_limit
--     ON public.event_promo_redemptions;
--   DROP FUNCTION IF EXISTS public.enforce_event_promo_redemption_limit();
--   -- and re-run the require_published_event_for_issued_ticket() definition
--   -- from 20260809214010_harden_event_access_ticket_lifecycle.sql.

create or replace function public.require_published_event_for_issued_ticket()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_event_status text;
begin
  if tg_op = 'INSERT'
     and coalesce(auth.jwt() ->> 'role', '') <> 'service_role'
     and not public.has_role('admin')
     and session_user not in ('postgres', 'supabase_admin') then
    raise exception using
      errcode = '42501',
      message = 'permission denied for table tickets';
  end if;

  if new.status <> 'issued' then
    return new;
  end if;

  -- Malformed client probes (e.g. RLS matrix DEFAULT VALUES) omit required FKs.
  -- Defer to NOT NULL / RLS so deny cells still surface as permission errors.
  if new.instance_id is null then
    return new;
  end if;

  select e.status
  into v_event_status
  from public.event_instances ei
  join public.events e on e.id = ei.event_id
  where ei.id = new.instance_id
  for share of e;

  if v_event_status is null then
    raise exception using
      errcode = '23503',
      message = 'ticket event instance does not exist';
  end if;

  if v_event_status = 'published' then
    return new;
  end if;

  -- Unpublished (draft) events: sold tickets stay valid. Existing issued
  -- credentials may still change (transfer / link to paid item) and paid
  -- credentials may still be issued; new unpaid claims may not.
  if v_event_status = 'draft' then
    if tg_op = 'UPDATE' and old.status = 'issued' then
      return new;
    end if;
    if tg_op = 'INSERT' and new.order_item_id is not null then
      return new;
    end if;
  end if;

  raise exception using
    errcode = '23514',
    message = 'tickets may be issued only for published events';
end;
$$;

comment on function public.require_published_event_for_issued_ticket() is
  'Rejects issued ticket credentials unless the parent event is published, or is '
  'unpublished (draft) and the write keeps an already-sold/paid credential valid.';

revoke all on function public.require_published_event_for_issued_ticket() from public;
revoke execute on function public.require_published_event_for_issued_ticket()
  from public, anon, authenticated;
grant execute on function public.require_published_event_for_issued_ticket()
  to postgres, service_role;

create or replace function public.enforce_event_promo_redemption_limit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_max integer;
  v_used integer;
begin
  -- Serialise redemptions of one code on its row lock.
  select pc.max_redemptions
  into v_max
  from public.event_promo_codes pc
  where pc.id = new.promo_id
  for update;

  if not found then
    raise exception using
      errcode = '23503',
      message = 'event promo code does not exist';
  end if;

  -- Same order replayed: let ON CONFLICT (order_id) DO NOTHING absorb it.
  if exists (
    select 1 from public.event_promo_redemptions r where r.order_id = new.order_id
  ) then
    return new;
  end if;

  if v_max is not null then
    select count(*)::integer
    into v_used
    from public.event_promo_redemptions r
    where r.promo_id = new.promo_id;

    if v_used >= v_max then
      raise exception using
        errcode = '23514',
        message = 'event_promo_redemption_limit_reached';
    end if;
  end if;

  return new;
end;
$$;

comment on function public.enforce_event_promo_redemption_limit() is
  'Locks the promo code row and refuses a redemption beyond max_redemptions.';

revoke all on function public.enforce_event_promo_redemption_limit() from public;
revoke execute on function public.enforce_event_promo_redemption_limit()
  from public, anon, authenticated;
grant execute on function public.enforce_event_promo_redemption_limit()
  to postgres, service_role;

drop trigger if exists event_promo_redemptions_enforce_limit
  on public.event_promo_redemptions;
create trigger event_promo_redemptions_enforce_limit
  before insert on public.event_promo_redemptions
  for each row
  execute function public.enforce_event_promo_redemption_limit();

insert into public.platform_config (key, value, description) values
  (
    'event_pre_event_advance_bps',
    '0'::jsonb,
    'Share (basis points, 0-5000) of a >14-day-ahead ticket order released to the '
    'organiser 7 days before the event. 0 = hold 100% until after the event ends '
    '(growth blueprint 7.3 control 1 / 7.4). Legacy behaviour was 5000 (50%).'
  )
on conflict (key) do nothing;
