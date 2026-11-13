-- Pay at the door by mobile money (growth blueprint §4, option C). Flag `pay_at_door`, default OFF.
--
-- When the rider arrives with a cash-on-delivery parcel, the rider (via ops) or
-- the customer (order page) asks Lenco for a mobile-money collection (USSD push)
-- of the order total to Convergeo's Lenco account. The customer's handover code
-- is released only once a VERIFIED observation (signed webhook or our own
-- status query) confirms the exact amount. Cash stays a capped fallback.
--
--   door_payment_sessions    one per delivery dispatch: arrival + how the order
--                            was settled at the door (mobile_money | cash).
--                            Settlement is write-once.
--   door_payment_attempts    one row per USSD push. Guarded status machine:
--                              initiated → pushed | successful | failed | expired
--                              pushed    → successful | failed | expired
--                              expired   → successful | failed   (late answer)
--                            At most one in-flight attempt per order.
--   door_payment_exceptions  money that arrived but cannot settle the order:
--                            order cancelled, already settled (cash or another
--                            push), amount/currency mismatch. Never revives the
--                            order; booked to the `door_payment_suspense` ledger
--                            account for ops to refund by payout.
--
-- Every insert / status change on sessions and attempts writes public.audit_log
-- (trigger), actor + note from transaction-local GUCs app.door_actor / app.door_note.
-- Writes are service-role only; admins may read; customers see the API projection.
--
-- Additive only: new tables, functions, triggers, one ledger account kind + row,
-- one feature_flags row, one platform_config row.
--
-- Down (manual; safe while unused — ledger_postings is ON DELETE RESTRICT, so the
-- account delete fails closed once money has moved):
--   drop table public.door_payment_exceptions, public.door_payment_attempts,
--     public.door_payment_sessions;
--   drop function public.guard_door_payment_sessions_update(),
--     public.guard_door_payment_attempts_update(), public.audit_door_payment_change();
--   delete from public.ledger_accounts where kind = 'door_payment_suspense' and vendor_id is null;
--   alter table public.ledger_accounts drop constraint ledger_accounts_kind_check;
--   alter table public.ledger_accounts add constraint ledger_accounts_kind_check
--     check (kind in ('platform_cash', 'escrow', 'commission_revenue',
--                     'vendor_payable', 'cod_receivable', 'fees', 'delivery_revenue'));
--   delete from public.feature_flags where flag = 'pay_at_door';
--   delete from public.platform_config where key in ('pay_at_door_max_attempts',
--     'pay_at_door_attempt_ttl_seconds');

-- ---------------------------------------------------------------------------
-- 1. Sessions (one per delivery dispatch)
-- ---------------------------------------------------------------------------

create table if not exists public.door_payment_sessions (
  dispatch_request_id uuid primary key
    references public.dispatch_requests (id) on delete restrict,
  order_id uuid not null references public.orders (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  arrived_at timestamptz,
  arrived_by uuid,
  settled_via text check (settled_via in ('mobile_money', 'cash')),
  settled_attempt_id uuid,
  settled_at timestamptz,
  settled_by uuid,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint door_payment_sessions_settled_check check (
    ((settled_via is null) = (settled_at is null))
    and (settled_via is distinct from 'mobile_money' or settled_attempt_id is not null)
    and (settled_via is distinct from 'cash' or settled_attempt_id is null)
  )
);

create index if not exists door_payment_sessions_order_idx
  on public.door_payment_sessions (order_id);

comment on table public.door_payment_sessions is
  'Pay at the door (flag pay_at_door): arrival + settlement per delivery dispatch. Settlement '
  'is write-once; written by app/services/payments/door.py (service role) only.';

-- ---------------------------------------------------------------------------
-- 2. Attempts (one per USSD push)
-- ---------------------------------------------------------------------------

create table if not exists public.door_payment_attempts (
  id uuid primary key default gen_random_uuid(),
  dispatch_request_id uuid not null
    references public.door_payment_sessions (dispatch_request_id) on delete restrict,
  order_id uuid not null references public.orders (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  phone_e164 text not null check (phone_e164 ~ '^\+260[79][0-9]{8}$'),
  operator text not null check (operator in ('mtn', 'airtel')),
  lenco_reference text not null unique
    check (lenco_reference ~ '^ord-[-._A-Za-z0-9]+$' and char_length(lenco_reference) <= 128),
  provider_reference text,
  status text not null default 'initiated'
    check (status in ('initiated', 'pushed', 'successful', 'failed', 'expired')),
  failure_reason text check (failure_reason is null or char_length(failure_reason) <= 200),
  observed_amount_ngwee bigint check (observed_amount_ngwee is null or observed_amount_ngwee >= 0),
  observation_source text check (observation_source is null
    or observation_source in ('webhook', 'status_query', 'initiation')),
  initiated_by uuid,
  initiated_role text not null check (initiated_role in ('customer', 'admin', 'system')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz
);

create unique index if not exists door_payment_attempts_one_in_flight_per_order
  on public.door_payment_attempts (order_id)
  where status in ('initiated', 'pushed');
create index if not exists door_payment_attempts_dispatch_idx
  on public.door_payment_attempts (dispatch_request_id, created_at);
create index if not exists door_payment_attempts_open_idx
  on public.door_payment_attempts (updated_at)
  where status in ('initiated', 'pushed', 'expired');

comment on table public.door_payment_attempts is
  'Pay at the door: one Lenco mobile-money collection (USSD push) per row. Guarded status '
  'machine; status changes only from the service role, audited in audit_log.';

-- ---------------------------------------------------------------------------
-- 3. Exception queue
-- ---------------------------------------------------------------------------

create table if not exists public.door_payment_exceptions (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid not null unique references public.door_payment_attempts (id) on delete restrict,
  order_id uuid not null references public.orders (id) on delete restrict,
  reason text not null check (reason in (
    'order_not_payable', 'already_settled', 'amount_mismatch', 'currency_mismatch')),
  expected_amount_ngwee bigint not null check (expected_amount_ngwee >= 0),
  observed_amount_ngwee bigint check (observed_amount_ngwee is null or observed_amount_ngwee >= 0),
  ledger_transaction_id uuid references public.ledger_transactions (id) on delete restrict,
  status text not null default 'open' check (status in ('open', 'resolved')),
  resolution_note text check (resolution_note is null or char_length(resolution_note) <= 1000),
  resolved_by uuid,
  resolved_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  constraint door_payment_exceptions_resolved_check check (
    (status = 'resolved') = (resolved_at is not null)
  )
);

create index if not exists door_payment_exceptions_open_idx
  on public.door_payment_exceptions (created_at)
  where status = 'open';

comment on table public.door_payment_exceptions is
  'Pay at the door: money Lenco confirmed that could not settle its order (cancelled, already '
  'settled, wrong amount). Held in ledger account door_payment_suspense until ops refunds it.';

-- ---------------------------------------------------------------------------
-- 4. updated_at
-- ---------------------------------------------------------------------------

drop trigger if exists door_payment_sessions_set_updated_at on public.door_payment_sessions;
create trigger door_payment_sessions_set_updated_at
  before update on public.door_payment_sessions
  for each row execute function public.set_updated_at();

drop trigger if exists door_payment_attempts_set_updated_at on public.door_payment_attempts;
create trigger door_payment_attempts_set_updated_at
  before update on public.door_payment_attempts
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 5. Guards (service role only; immutable money fields; legal transitions)
-- ---------------------------------------------------------------------------

create or replace function public.guard_door_payment_sessions_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user not in ('postgres', 'supabase_admin') and jwt_role <> 'service_role' then
    raise exception 'door_payment_sessions are server-controlled' using errcode = '42501';
  end if;
  if new.order_id is distinct from old.order_id
     or new.amount_ngwee is distinct from old.amount_ngwee then
    raise exception 'door payment session order/amount are immutable' using errcode = '23514';
  end if;
  if old.arrived_at is not null and new.arrived_at is distinct from old.arrived_at then
    raise exception 'door payment arrival is write-once' using errcode = '23514';
  end if;
  if old.settled_via is not null and (
       new.settled_via is distinct from old.settled_via
       or new.settled_attempt_id is distinct from old.settled_attempt_id
       or new.settled_at is distinct from old.settled_at) then
    raise exception 'door payment settlement is write-once' using errcode = '23514';
  end if;
  return new;
end;
$$;

drop trigger if exists door_payment_sessions_guard_update on public.door_payment_sessions;
create trigger door_payment_sessions_guard_update
  before update on public.door_payment_sessions
  for each row execute function public.guard_door_payment_sessions_update();

create or replace function public.guard_door_payment_attempts_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
  allowed boolean;
begin
  if session_user not in ('postgres', 'supabase_admin') and jwt_role <> 'service_role' then
    raise exception 'door_payment_attempts are server-controlled' using errcode = '42501';
  end if;
  if new.order_id is distinct from old.order_id
     or new.dispatch_request_id is distinct from old.dispatch_request_id
     or new.amount_ngwee is distinct from old.amount_ngwee
     or new.lenco_reference is distinct from old.lenco_reference
     or new.phone_e164 is distinct from old.phone_e164
     or new.operator is distinct from old.operator then
    raise exception 'door payment attempt identity is immutable' using errcode = '23514';
  end if;
  if new.status is not distinct from old.status then
    return new;
  end if;
  allowed := (old.status, new.status) in (
    ('initiated', 'pushed'),
    ('initiated', 'successful'),
    ('initiated', 'failed'),
    ('initiated', 'expired'),
    ('pushed', 'successful'),
    ('pushed', 'failed'),
    ('pushed', 'expired'),
    ('expired', 'successful'),
    ('expired', 'failed')
  );
  if not allowed then
    raise exception 'invalid door payment transition % -> %', old.status, new.status
      using errcode = '23514';
  end if;
  if new.status in ('successful', 'failed') then
    new.completed_at := coalesce(new.completed_at, timezone('utc', now()));
  end if;
  return new;
end;
$$;

drop trigger if exists door_payment_attempts_guard_update on public.door_payment_attempts;
create trigger door_payment_attempts_guard_update
  before update on public.door_payment_attempts
  for each row execute function public.guard_door_payment_attempts_update();

-- ---------------------------------------------------------------------------
-- 6. Audit (insert + status/settlement change → audit_log)
-- ---------------------------------------------------------------------------

create or replace function public.audit_door_payment_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  actor_raw text := nullif(current_setting('app.door_actor', true), '');
  note_raw text := nullif(current_setting('app.door_note', true), '');
  actor_id uuid;
  entity uuid;
  action_name text;
  before_doc jsonb;
  after_doc jsonb;
begin
  if actor_raw is not null and actor_raw ~ '^[0-9a-fA-F-]{36}$' then
    actor_id := actor_raw::uuid;
  end if;

  if tg_table_name = 'door_payment_attempts' then
    entity := new.id;
    if tg_op = 'INSERT' then
      action_name := 'door_payment.attempt.created';
      before_doc := null;
    elsif new.status is distinct from old.status then
      action_name := 'door_payment.attempt.' || new.status;
      before_doc := jsonb_build_object('status', old.status);
    else
      return new;
    end if;
    after_doc := jsonb_build_object(
      'status', new.status, 'order_id', new.order_id, 'amount_ngwee', new.amount_ngwee,
      'operator', new.operator, 'failure_reason', new.failure_reason,
      'observed_amount_ngwee', new.observed_amount_ngwee,
      'observation_source', new.observation_source, 'note', note_raw);
  else
    entity := new.dispatch_request_id;
    if tg_op = 'INSERT' then
      action_name := 'door_payment.session.opened';
      before_doc := null;
    elsif new.settled_via is distinct from old.settled_via then
      action_name := 'door_payment.session.settled';
      before_doc := jsonb_build_object('settled_via', old.settled_via);
    elsif new.arrived_at is distinct from old.arrived_at then
      action_name := 'door_payment.session.arrived';
      before_doc := jsonb_build_object('arrived_at', old.arrived_at);
    else
      return new;
    end if;
    after_doc := jsonb_build_object(
      'order_id', new.order_id, 'amount_ngwee', new.amount_ngwee,
      'arrived_at', new.arrived_at, 'settled_via', new.settled_via,
      'settled_attempt_id', new.settled_attempt_id, 'note', note_raw);
  end if;

  insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
  values (actor_id, action_name, tg_table_name, entity, before_doc, after_doc);
  return new;
end;
$$;

drop trigger if exists door_payment_attempts_audit on public.door_payment_attempts;
create trigger door_payment_attempts_audit
  after insert or update on public.door_payment_attempts
  for each row execute function public.audit_door_payment_change();

drop trigger if exists door_payment_sessions_audit on public.door_payment_sessions;
create trigger door_payment_sessions_audit
  after insert or update on public.door_payment_sessions
  for each row execute function public.audit_door_payment_change();

revoke all on function public.guard_door_payment_sessions_update() from public, anon, authenticated;
revoke all on function public.guard_door_payment_attempts_update() from public, anon, authenticated;
revoke all on function public.audit_door_payment_change() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 7. RLS + grants (admins read; writes service role only)
-- ---------------------------------------------------------------------------

alter table public.door_payment_sessions enable row level security;
alter table public.door_payment_attempts enable row level security;
alter table public.door_payment_exceptions enable row level security;

drop policy if exists door_payment_sessions_admin_select on public.door_payment_sessions;
create policy door_payment_sessions_admin_select
  on public.door_payment_sessions for select to authenticated
  using (public.has_role('admin'));

drop policy if exists door_payment_attempts_admin_select on public.door_payment_attempts;
create policy door_payment_attempts_admin_select
  on public.door_payment_attempts for select to authenticated
  using (public.has_role('admin'));

drop policy if exists door_payment_exceptions_admin_select on public.door_payment_exceptions;
create policy door_payment_exceptions_admin_select
  on public.door_payment_exceptions for select to authenticated
  using (public.has_role('admin'));

revoke all on table public.door_payment_sessions from anon, authenticated;
revoke all on table public.door_payment_attempts from anon, authenticated;
revoke all on table public.door_payment_exceptions from anon, authenticated;
grant select on public.door_payment_sessions to authenticated;
grant select on public.door_payment_attempts to authenticated;
grant select on public.door_payment_exceptions to authenticated;
grant all on public.door_payment_sessions to service_role;
grant all on public.door_payment_attempts to service_role;
grant all on public.door_payment_exceptions to service_role;

-- ---------------------------------------------------------------------------
-- 8. Ledger: suspense account for exception money
-- ---------------------------------------------------------------------------

alter table public.ledger_accounts drop constraint if exists ledger_accounts_kind_check;
alter table public.ledger_accounts add constraint ledger_accounts_kind_check
  check (kind in (
    'platform_cash', 'escrow', 'commission_revenue',
    'vendor_payable', 'cod_receivable', 'fees',
    'delivery_revenue', 'door_payment_suspense'
  ));

insert into public.ledger_accounts (id, kind)
values ('c7000000-0000-0000-0000-000000000008', 'door_payment_suspense')
on conflict (kind) where vendor_id is null do nothing;

-- ---------------------------------------------------------------------------
-- 9. Flag (default OFF) + config
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  (
    'pay_at_door',
    false,
    'Pay at the door by mobile money: rider/customer triggers a Lenco USSD push at delivery; '
    'the handover code is released only after a verified payment. Cash stays a capped fallback. '
    'Default OFF = existing COD behaviour unchanged.'
  )
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  ('pay_at_door_max_attempts', '3'::jsonb,
   'Most mobile-money prompts per delivery before the rider must switch to the cash fallback.'),
  ('pay_at_door_attempt_ttl_seconds', '120'::jsonb,
   'Seconds an unanswered mobile-money prompt stays live before a new one may be sent.')
on conflict (key) do nothing;
