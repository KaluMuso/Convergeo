-- Free events + free services (founder decision: price 0, no commission, no payment).
--
-- Events already model free tickets as ticket_types.kind = 'free_rsvp' (price 0,
-- enforced by ticket_types_free_rsvp_price_chk since 0004). This migration adds:
--   1. public.event_rsvps — one RSVP per (event, user); the idempotency anchor for
--      POST /tickets/rsvp (a replay returns the existing order/tickets).
--   2. public.services.is_free + services_free_price_check — a free service has no
--      from/booking price and is never "bookable" (the paid deposit path).
--   3. public.service_free_bookings — a free service request the vendor accepts or
--      declines; status moves only through public.transition_service_free_booking
--      (guarded, audited). No job/quote/order/payment is created.
--   4. Money guards: private.order_is_free + BEFORE INSERT triggers that refuse a
--      ledger transaction for a free order and a payment for a checkout group made
--      only of free orders (defence in depth behind the API).
--   5. Rate scopes ticket_rsvp_ip, ticket_rsvp_user, service_free_booking_respond in
--      BOTH private.rate_counter_scope_manifest and rate_counters_scope_check. The
--      constraint is rebuilt from the manifest so no previously-allowed scope drops.
--
-- Additive + reversible. Down (in order):
--   drop trigger if exists payments_reject_free_group on public.payments;
--   drop trigger if exists ledger_transactions_reject_free_order on public.ledger_transactions;
--   drop function if exists private.reject_payment_for_free_group();
--   drop function if exists private.reject_ledger_for_free_order();
--   drop function if exists private.order_is_free(uuid);
--   drop function if exists public.transition_service_free_booking(uuid, text, uuid);
--   drop table if exists public.service_free_bookings;   -- cascades policies/triggers
--   drop function if exists private.guard_service_free_booking_status();
--   alter table public.services drop constraint if exists services_free_price_check,
--     drop column if exists is_free;
--   drop table if exists public.event_rsvps;
--   delete from private.rate_counter_scope_manifest where scope in
--     ('ticket_rsvp_ip','ticket_rsvp_user','service_free_booking_respond');
--   then rebuild rate_counters_scope_check from the manifest (same DO block as below;
--   only safe once no rate_counters rows use the three scopes).

-- ---------------------------------------------------------------------------
-- 5. Rate scopes (manifest + constraint, rebuilt from the manifest).
-- ---------------------------------------------------------------------------
insert into private.rate_counter_scope_manifest (scope) values
  ('service_free_booking_respond'),
  ('ticket_rsvp_ip'),
  ('ticket_rsvp_user')
on conflict (scope) do nothing;

do $$
declare
  scope_list text;
begin
  select string_agg(quote_literal(scope), ', ' order by scope)
    into scope_list
    from private.rate_counter_scope_manifest;
  execute 'alter table public.rate_counters drop constraint if exists rate_counters_scope_check';
  execute format(
    'alter table public.rate_counters add constraint rate_counters_scope_check check (scope in (%s))',
    scope_list
  );
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Event RSVPs: one per user per event.
-- ---------------------------------------------------------------------------
create table public.event_rsvps (
  event_id uuid not null references public.events (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  instance_id uuid not null references public.event_instances (id) on delete cascade,
  ticket_type_id uuid not null references public.ticket_types (id) on delete cascade,
  order_id uuid references public.orders (id) on delete set null,
  qty int not null check (qty between 1 and 4),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (event_id, user_id)
);

create index event_rsvps_user_id_idx on public.event_rsvps (user_id);

comment on table public.event_rsvps is
  'One free RSVP per (event, user). Written only by the API (service role); a '
  'replayed RSVP returns the existing order. qty is capped at 4 tickets per user.';

alter table public.event_rsvps enable row level security;
alter table public.event_rsvps force row level security;

create policy event_rsvps_own_select
  on public.event_rsvps
  for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy event_rsvps_organiser_select
  on public.event_rsvps
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_rsvps.event_id
        and v.owner_user_id = (select auth.uid())
    )
  );

-- D1 (20261115140100): admins read; every write goes through the API.
create policy event_rsvps_admin_select
  on public.event_rsvps
  for select
  to authenticated
  using (public.has_role('admin'));

revoke all on public.event_rsvps from anon;
grant select on public.event_rsvps to authenticated;
grant select, insert, update, delete on public.event_rsvps to service_role;

-- ---------------------------------------------------------------------------
-- 2. Free services.
-- ---------------------------------------------------------------------------
alter table public.services
  add column if not exists is_free boolean not null default false;

alter table public.services
  drop constraint if exists services_free_price_check;
alter table public.services
  add constraint services_free_price_check
  check (
    not is_free
    or (from_price_ngwee is null and booking_price_ngwee is null and not bookable)
  );

comment on column public.services.is_free is
  'Free service: no price, no commission, no payment. Customers send a free booking '
  'request (public.service_free_bookings) that the vendor accepts or declines.';

-- ---------------------------------------------------------------------------
-- 3. Free service booking requests.
-- ---------------------------------------------------------------------------
create table public.service_free_bookings (
  id uuid primary key default gen_random_uuid(),
  service_id uuid not null references public.services (id) on delete cascade,
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  customer_id uuid not null references auth.users (id) on delete cascade,
  idempotency_key text not null check (char_length(idempotency_key) between 8 and 128),
  note text check (note is null or char_length(note) <= 2000),
  preferred_date date,
  status text not null default 'requested'
    check (status in ('requested', 'accepted', 'declined', 'cancelled')),
  responded_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint service_free_bookings_idem_key unique (customer_id, service_id, idempotency_key)
);

-- Anti-abuse: at most one open request per customer per service.
create unique index service_free_bookings_one_open_idx
  on public.service_free_bookings (customer_id, service_id)
  where status = 'requested';
create index service_free_bookings_vendor_status_idx
  on public.service_free_bookings (vendor_id, status, created_at desc);

create trigger service_free_bookings_set_updated_at
  before update on public.service_free_bookings
  for each row
  execute function public.set_updated_at();

-- Status changes only via public.transition_service_free_booking (sets a txn GUC).
create or replace function private.guard_service_free_booking_status()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status is distinct from old.status
     and coalesce(current_setting('vergeo.free_booking_transition', true), '') <> '1' then
    raise exception 'service_free_bookings.status changes only via transition_service_free_booking'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger service_free_bookings_guard_status
  before update on public.service_free_bookings
  for each row
  execute function private.guard_service_free_booking_status();

alter table public.service_free_bookings enable row level security;
alter table public.service_free_bookings force row level security;

create policy service_free_bookings_customer_select
  on public.service_free_bookings
  for select
  to authenticated
  using (customer_id = (select auth.uid()));

create policy service_free_bookings_vendor_select
  on public.service_free_bookings
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = service_free_bookings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

-- D1 (20261115140100): admins read; every write goes through the API.
create policy service_free_bookings_admin_select
  on public.service_free_bookings
  for select
  to authenticated
  using (public.has_role('admin'));

revoke all on public.service_free_bookings from anon;
grant select on public.service_free_bookings to authenticated;
grant select, insert, update on public.service_free_bookings to service_role;

create or replace function public.transition_service_free_booking(
  p_booking_id uuid,
  p_to text,
  p_actor uuid
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  b public.service_free_bookings%rowtype;
  is_vendor boolean;
begin
  select * into b from public.service_free_bookings where id = p_booking_id for update;
  if not found then
    raise exception 'free booking not found' using errcode = 'P0002';
  end if;
  select exists (
    select 1 from public.vendors v where v.id = b.vendor_id and v.owner_user_id = p_actor
  ) into is_vendor;

  if p_to in ('accepted', 'declined') then
    if not is_vendor then
      raise exception 'only the vendor may respond' using errcode = '42501';
    end if;
    if b.status <> 'requested' then
      raise exception 'invalid transition % -> %', b.status, p_to using errcode = '55000';
    end if;
  elsif p_to = 'cancelled' then
    if b.customer_id is distinct from p_actor then
      raise exception 'only the customer may cancel' using errcode = '42501';
    end if;
    if b.status not in ('requested', 'accepted') then
      raise exception 'invalid transition % -> %', b.status, p_to using errcode = '55000';
    end if;
  else
    raise exception 'unknown target status %', p_to using errcode = '22023';
  end if;

  perform set_config('vergeo.free_booking_transition', '1', true);
  update public.service_free_bookings
     set status = p_to,
         responded_at = case when p_to in ('accepted', 'declined')
                             then timezone('utc', now()) else responded_at end
   where id = p_booking_id;
  perform set_config('vergeo.free_booking_transition', '', true);

  insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
  values (
    p_actor, 'service_free_booking.' || p_to, 'service_free_booking', p_booking_id,
    jsonb_build_object('status', b.status), jsonb_build_object('status', p_to)
  );
  return p_to;
end;
$$;

revoke all on function public.transition_service_free_booking(uuid, text, uuid)
  from public, anon, authenticated;
grant execute on function public.transition_service_free_booking(uuid, text, uuid)
  to service_role;

-- ---------------------------------------------------------------------------
-- 4. Money guards: no ledger / payment for free orders.
-- ---------------------------------------------------------------------------
create or replace function private.order_is_free(p_order_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  -- A genuinely free order: created by the RSVP / free-booking paths (snapshot
  -- is_free = true), no delivery fee, and no line with a price. A zero-commission
  -- category (e.g. free_events) is NOT free: its paid tickets still move money.
  select coalesce((
    select (o.commission_snapshot ->> 'is_free') = 'true'
       and coalesce(o.delivery_fee_ngwee, 0) = 0
       and not exists (
         select 1 from public.order_items oi
         where oi.order_id = o.id and oi.unit_price_ngwee > 0
       )
    from public.orders o
    where o.id = p_order_id
  ), false);
$$;

create or replace function private.reject_ledger_for_free_order()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.order_id is not null and private.order_is_free(new.order_id) then
    raise exception 'free order % cannot carry ledger postings', new.order_id
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger ledger_transactions_reject_free_order
  before insert on public.ledger_transactions
  for each row
  execute function private.reject_ledger_for_free_order();

create or replace function private.reject_payment_for_free_group()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (select 1 from public.orders o where o.checkout_group_id = new.checkout_group_id)
     and not exists (
       select 1 from public.orders o
       where o.checkout_group_id = new.checkout_group_id
         and not private.order_is_free(o.id)
     ) then
    raise exception 'checkout group % is free; no payment intent allowed', new.checkout_group_id
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger payments_reject_free_group
  before insert on public.payments
  for each row
  execute function private.reject_payment_for_free_group();

revoke all on function private.order_is_free(uuid) from public, anon, authenticated;
revoke all on function private.reject_ledger_for_free_order() from public, anon, authenticated;
revoke all on function private.reject_payment_for_free_group() from public, anon, authenticated;
revoke all on function private.guard_service_free_booking_status() from public, anon, authenticated;
