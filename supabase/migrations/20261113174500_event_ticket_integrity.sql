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
-- 3. Tiered organiser advance policy + organiser receivable (section 3 below).
--
-- Additive only (function body replaced in place, new triggers/functions/tables,
-- ledger kind checks widened to a strict superset, config rows on conflict do
-- nothing).
--
-- Reversible rollback (manual; the ledger part fails closed once money moved,
-- because ledger_postings references accounts ON DELETE RESTRICT):
--   DELETE FROM public.platform_config WHERE key IN (
--     'event_verified_organiser_advance_bps', 'event_advance_min_kyc_tier',
--     'event_advance_repayment_days');
--   DROP TABLE IF EXISTS public.organiser_advance_debts;
--   DROP TABLE IF EXISTS public.organiser_advance_undertakings;
--   DELETE FROM public.ledger_accounts la WHERE la.kind = 'organiser_receivable'
--     AND NOT EXISTS (SELECT 1 FROM public.ledger_postings lp WHERE lp.account_id = la.id);
--   -- then restore both ledger_accounts checks from
--   -- 20261113120500_delivery_revenue_ledger_account.sql / 0006_money.sql.
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

-- ---------------------------------------------------------------------------
-- 3. Tiered organiser advance policy + organiser receivable
-- ---------------------------------------------------------------------------
-- Unverified organisers: 100% of ticket money held until after the event.
-- Verified organisers (approved KYC tier >= event_advance_min_kyc_tier, active,
-- signed the advance undertaking, no unpaid/blacklisted advance debt): up to
-- event_verified_organiser_advance_bps released 7 days before the event.
-- If such an event is cancelled, the released advance (plus the platform's
-- captured commission/fee) is put back into the order's escrow so buyers are
-- refunded in full from platform funds; the organiser's share is recorded as an
-- organiser_receivable (vendor ledger account) and an organiser_advance_debts row.
-- Unpaid past event_advance_repayment_days -> vendor suspended, debt blacklisted
-- and flagged for legal follow-up (API sweeper, audited).

alter table public.ledger_accounts drop constraint if exists ledger_accounts_kind_check;
alter table public.ledger_accounts add constraint ledger_accounts_kind_check
  check (kind in (
    'platform_cash', 'escrow', 'commission_revenue',
    'vendor_payable', 'cod_receivable', 'fees',
    'delivery_revenue', 'organiser_receivable'
  ));

alter table public.ledger_accounts drop constraint if exists ledger_accounts_vendor_kind_check;
alter table public.ledger_accounts add constraint ledger_accounts_vendor_kind_check check (
  (kind in ('vendor_payable', 'cod_receivable', 'organiser_receivable') and vendor_id is not null)
  or (kind not in ('vendor_payable', 'cod_receivable', 'organiser_receivable') and vendor_id is null)
);

create table if not exists public.organiser_advance_undertakings (
  vendor_id uuid primary key references public.vendors (id) on delete restrict,
  terms_version text not null check (length(trim(terms_version)) > 0),
  accepted_by uuid not null references auth.users (id) on delete restrict,
  accepted_at timestamptz not null default timezone('utc', now()),
  revoked_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

comment on table public.organiser_advance_undertakings is
  'Organiser acceptance of the pre-event advance undertaking: if the event is cancelled '
  'or fails, buyers are refunded by the platform and the organiser repays the advance.';

create trigger organiser_advance_undertakings_set_updated_at
  before update on public.organiser_advance_undertakings
  for each row execute function public.set_updated_at();

create table if not exists public.organiser_advance_debts (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete restrict,
  event_id uuid not null references public.events (id) on delete restrict,
  order_id uuid not null references public.orders (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  recovered_ngwee bigint not null default 0
    check (recovered_ngwee >= 0 and recovered_ngwee <= amount_ngwee),
  status text not null default 'open' check (status in ('open', 'settled', 'written_off')),
  due_at timestamptz not null,
  suspended_at timestamptz,
  blacklisted_at timestamptz,
  legal_followup_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint organiser_advance_debts_order_key unique (order_id),
  constraint organiser_advance_debts_settled_check
    check (status <> 'settled' or recovered_ngwee = amount_ngwee)
);

create index if not exists organiser_advance_debts_vendor_open_idx
  on public.organiser_advance_debts (vendor_id, due_at) where status = 'open';

comment on table public.organiser_advance_debts is
  'Advance released to an organiser before an event that was later cancelled; mirrors '
  'the organiser_receivable ledger account per order. Written only by the API.';

create trigger organiser_advance_debts_set_updated_at
  before update on public.organiser_advance_debts
  for each row execute function public.set_updated_at();

alter table public.organiser_advance_undertakings enable row level security;
alter table public.organiser_advance_undertakings force row level security;
alter table public.organiser_advance_debts enable row level security;
alter table public.organiser_advance_debts force row level security;
revoke all on table public.organiser_advance_undertakings, public.organiser_advance_debts
  from anon, authenticated;
grant all on table public.organiser_advance_undertakings, public.organiser_advance_debts
  to service_role;

insert into public.platform_config (key, value, description) values
  (
    'event_verified_organiser_advance_bps',
    '5000'::jsonb,
    'Max share (bps, capped at 5000) of a >14-day-ahead ticket order released 7 days '
    'before the event to a VERIFIED organiser who signed the advance undertaking. '
    'Unverified organisers always get 0 (100% held until after the event). 0 here '
    'disables advances for everyone.'
  ),
  (
    'event_advance_min_kyc_tier',
    '2'::jsonb,
    'Minimum approved KYC tier for an organiser to qualify for a pre-event advance.'
  ),
  (
    'event_advance_repayment_days',
    '14'::jsonb,
    'Days an organiser has to repay a recovered advance before automatic suspension, '
    'blacklisting and a legal follow-up flag.'
  )
on conflict (key) do nothing;
