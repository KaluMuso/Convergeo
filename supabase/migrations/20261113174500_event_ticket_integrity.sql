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
-- 4. Guarded vendor suspension function used by the overdue-advance sweeper.
--
-- 5. Guard: organiser_receivable can never be credited below zero (atomic
--    repayment / offset limit under concurrency).
--
-- Additive only (function body replaced in place, new triggers/functions/tables,
-- ledger kind checks widened to a strict superset, config rows on conflict do
-- nothing).
--
-- Reversible rollback (manual; the ledger part fails closed once money moved,
-- because ledger_postings references accounts ON DELETE RESTRICT):
--   DELETE FROM public.platform_config WHERE key IN (
--     'event_verified_organiser_advance_bps', 'event_advance_min_kyc_tier',
--     'event_advance_repayment_days', 'event_advance_min_successful_events');
--   DELETE FROM public.feature_flags WHERE flag = 'event_organiser_advance';
--   DROP FUNCTION IF EXISTS public.transition_vendor_suspend(uuid, uuid, text, jsonb);
--   DROP TRIGGER IF EXISTS ledger_postings_organiser_receivable_guard ON public.ledger_postings;
--   DROP FUNCTION IF EXISTS public.guard_organiser_receivable_not_overdrawn();
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
-- Gated by feature_flags.event_organiser_advance (default OFF).
-- Verified organisers (approved KYC tier >= event_advance_min_kyc_tier, active,
-- track record >= event_advance_min_successful_events, signed the advance
-- undertaking, no unpaid/blacklisted advance debt): up to
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
  ),
  (
    'event_advance_min_successful_events',
    '2'::jsonb,
    'Track record: completed events with at least one successful paid ticket sale an '
    'organiser needs before qualifying for a pre-event advance. 0 = KYC tier only.'
  )
on conflict (key) do nothing;

-- Kill switch for the whole tiered advance (default OFF): while off, every
-- organiser is held 100% until after the event regardless of the config above.
insert into public.feature_flags (flag, enabled, description) values
  (
    'event_organiser_advance',
    false,
    'Tiered organiser pre-event advance for verified organisers with a track record '
    '(event_verified_organiser_advance_bps, 7 days before the event, repayable if the '
    'event is cancelled). Default OFF = everyone is paid after the event.'
  )
on conflict (flag) do nothing;

-- ---------------------------------------------------------------------------
-- 4. Guarded vendor suspension (CLAUDE.md rule 4: no raw status UPDATEs)
-- ---------------------------------------------------------------------------
-- The only server-side path that suspends a vendor for an overdue advance debt.
-- Locks the vendor row, allows exactly active -> suspended, and writes the
-- audit_log row in the same transaction as the status change. Outcomes:
--   'suspended'          the vendor was active and is now suspended (audited);
--   'already_suspended'  no change, no audit row;
--   'not_active'         any other status (draft, pending_kyc, suspended_compliance,
--                        ...): no change, no audit row — never forced.
-- An unknown vendor raises vendor_not_found (SQLSTATE P0002).
-- Rollback: DROP FUNCTION public.transition_vendor_suspend(uuid, uuid, text, jsonb);
create or replace function public.transition_vendor_suspend(
  p_vendor_id uuid,
  p_actor uuid,
  p_reason text,
  p_details jsonb default '{}'::jsonb
)
returns text
language plpgsql
set search_path = public
as $$
declare
  v_status text;
begin
  if p_reason is null or btrim(p_reason) = '' then
    raise exception 'suspension reason is required' using errcode = '22023';
  end if;

  select status into v_status
  from public.vendors
  where id = p_vendor_id
  for update;

  if not found then
    raise exception 'vendor_not_found' using errcode = 'P0002';
  end if;

  if v_status = 'suspended' then
    return 'already_suspended';
  end if;
  if v_status <> 'active' then
    return 'not_active';
  end if;

  update public.vendors
  set status = 'suspended', updated_at = timezone('utc', now())
  where id = p_vendor_id and status = 'active';

  insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
  values (
    p_actor,
    'vendor.suspended',
    'vendor',
    p_vendor_id,
    jsonb_build_object('status', v_status),
    jsonb_build_object('status', 'suspended', 'reason', p_reason)
      || coalesce(p_details, '{}'::jsonb)
  );
  return 'suspended';
end;
$$;

comment on function public.transition_vendor_suspend(uuid, uuid, text, jsonb) is
  'Guarded vendor transition active -> suspended with audit_log row (server only).';

revoke all on function public.transition_vendor_suspend(uuid, uuid, text, jsonb) from public;
revoke execute on function public.transition_vendor_suspend(uuid, uuid, text, jsonb)
  from anon, authenticated;
grant execute on function public.transition_vendor_suspend(uuid, uuid, text, jsonb)
  to service_role;

-- ---------------------------------------------------------------------------
-- 5. Organiser receivable can never be overdrawn (atomic repayment limit)
-- ---------------------------------------------------------------------------
-- Repayments (organiser_receivable_repaid) and offsets (..._offset) credit the
-- organiser_receivable account. The API checks "amount <= what is owed" first, but
-- two concurrent repayments could both pass that read. This BEFORE INSERT guard
-- locks the receivable's ledger_accounts row (FOR UPDATE) and re-sums the account
-- under the lock; each plpgsql statement takes a fresh READ COMMITTED snapshot, so
-- a waiter sees the credit committed by the lock holder. A credit that would take
-- the balance below zero raises SQLSTATE 23514 'organiser_receivable_overdrawn'
-- and the whole ledger transaction rolls back.
-- Rollback: DROP TRIGGER IF EXISTS ledger_postings_organiser_receivable_guard
--   ON public.ledger_postings;
--   DROP FUNCTION IF EXISTS public.guard_organiser_receivable_not_overdrawn();
create or replace function public.guard_organiser_receivable_not_overdrawn()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_kind text;
  v_balance bigint;
begin
  if new.amount_ngwee >= 0 then
    return new;
  end if;

  select kind into v_kind
  from public.ledger_accounts
  where id = new.account_id;
  if v_kind is distinct from 'organiser_receivable' then
    return new;
  end if;

  perform 1 from public.ledger_accounts where id = new.account_id for update;

  select coalesce(sum(amount_ngwee), 0) into v_balance
  from public.ledger_postings
  where account_id = new.account_id;

  if v_balance + new.amount_ngwee < 0 then
    raise exception 'organiser_receivable_overdrawn'
      using errcode = '23514',
            detail = format('balance %s, credit %s', v_balance, -new.amount_ngwee);
  end if;
  return new;
end;
$$;

drop trigger if exists ledger_postings_organiser_receivable_guard on public.ledger_postings;
create trigger ledger_postings_organiser_receivable_guard
  before insert on public.ledger_postings
  for each row
  execute function public.guard_organiser_receivable_not_overdrawn();

revoke all on function public.guard_organiser_receivable_not_overdrawn() from public;
revoke execute on function public.guard_organiser_receivable_not_overdrawn()
  from anon, authenticated;
