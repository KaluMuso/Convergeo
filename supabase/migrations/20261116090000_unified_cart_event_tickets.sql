-- Unified cart & checkout, slice 1: event tickets in the cart (flag-free data
-- layer; the API refuses ticket lines unless the event is purchasable).
--
-- One checkout now pays for products and event tickets together. Each kind
-- keeps its own order, money rules and lifecycle:
--   * product lines  -> the per-vendor "goods" order (unchanged),
--   * ticket lines   -> a separate "ticket" order for the organiser, built by
--                       the same order transaction, with item_kind 'ticket' +
--                       order_item_tickets, the ticket commission snapshot
--                       (event_tickets / free_events rate, fee payer, buyer
--                       platform fee) and the capacity claim ids, so issuance
--                       (QR), event-date escrow release and refunds treat it
--                       exactly like a ticket bought on its own.
--
--   cart_ticket_items       ticket lines in a cart (one event instance per cart:
--                           one GMV reservation and one settlement anchor per
--                           checkout). Client roles read their own lines; only
--                           the service role (API) writes them, like cart_items
--                           since 0086 — the price is never client-supplied.
--   checkout_ticket_holds   capacity claimed for a checkout session (ticket ids
--                           claimed under the instance lock at session start);
--                           consumed once by order placement, voided on
--                           supersede/abandon, and swept at TTL by the existing
--                           stale-claim sweeper. Service role only.
--   orders.order_lane       'goods' | 'ticket'. The one-order-per-vendor unique
--                           index (0031) becomes one order per vendor per lane,
--                           so an organiser who also sells products gets two
--                           orders in one checkout instead of a mixed order.
--
-- Additive. Reversible (safe while no checkout group holds two lanes for one
-- vendor; check first with
--   select checkout_group_id, vendor_id from public.orders
--   group by 1, 2 having count(*) > 1;):
--   drop index if exists public.orders_checkout_group_vendor_lane_key;
--   create unique index if not exists orders_checkout_group_vendor_key
--     on public.orders (checkout_group_id, vendor_id);
--   alter table public.orders drop constraint if exists orders_order_lane_check;
--   alter table public.orders drop column if exists order_lane;
--   drop table if exists public.checkout_ticket_holds;
--   drop trigger if exists cart_ticket_items_one_instance on public.cart_ticket_items;
--   drop function if exists public.cart_ticket_items_one_instance();
--   drop table if exists public.cart_ticket_items;

-- ---------------------------------------------------------------------------
-- 1. cart_ticket_items
-- ---------------------------------------------------------------------------

create table if not exists public.cart_ticket_items (
  id uuid primary key default gen_random_uuid(),
  cart_id uuid not null references public.carts (id) on delete cascade,
  ticket_type_id uuid not null references public.ticket_types (id) on delete cascade,
  instance_id uuid not null references public.event_instances (id) on delete cascade,
  event_id uuid not null references public.events (id) on delete cascade,
  qty integer not null,
  attendee_names jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint cart_ticket_items_qty_check check (qty between 1 and 20),
  constraint cart_ticket_items_names_check
    check (
      attendee_names is null
      or (jsonb_typeof(attendee_names) = 'array' and jsonb_array_length(attendee_names) = qty)
    ),
  constraint cart_ticket_items_line_key unique (cart_id, ticket_type_id, instance_id)
);

create index if not exists cart_ticket_items_cart_idx on public.cart_ticket_items (cart_id);
create index if not exists cart_ticket_items_instance_idx
  on public.cart_ticket_items (instance_id);

drop trigger if exists cart_ticket_items_set_updated_at on public.cart_ticket_items;
create trigger cart_ticket_items_set_updated_at
  before update on public.cart_ticket_items
  for each row execute function public.set_updated_at();

comment on table public.cart_ticket_items is
  'Event ticket lines in a cart (unified checkout). Price is resolved server-side at '
  'every read; one event instance per cart. Service-role writes only.';

-- Every ticket line of a cart is for the same event instance, and the type
-- belongs to that instance's event.
create or replace function public.cart_ticket_items_one_instance()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_type_event uuid;
  v_instance_event uuid;
begin
  select tt.event_id into v_type_event from public.ticket_types tt where tt.id = new.ticket_type_id;
  select ei.event_id into v_instance_event
  from public.event_instances ei where ei.id = new.instance_id;
  if v_type_event is distinct from new.event_id
     or v_instance_event is distinct from new.event_id then
    raise exception 'CART_TICKET_EVENT_MISMATCH' using errcode = '23514';
  end if;
  if exists (
    select 1 from public.cart_ticket_items c
    where c.cart_id = new.cart_id
      and c.id <> new.id
      and c.instance_id <> new.instance_id
  ) then
    raise exception 'CART_TICKETS_ONE_EVENT' using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke execute on function public.cart_ticket_items_one_instance()
  from public, anon, authenticated;

drop trigger if exists cart_ticket_items_one_instance on public.cart_ticket_items;
create trigger cart_ticket_items_one_instance
  before insert or update on public.cart_ticket_items
  for each row execute function public.cart_ticket_items_one_instance();

alter table public.cart_ticket_items enable row level security;
alter table public.cart_ticket_items force row level security;

drop policy if exists cart_ticket_items_owner_select on public.cart_ticket_items;
create policy cart_ticket_items_owner_select
  on public.cart_ticket_items
  for select
  to authenticated
  using (
    exists (
      select 1 from public.carts c
      where c.id = cart_ticket_items.cart_id and c.user_id = (select auth.uid())
    )
  );

revoke all on public.cart_ticket_items from public, anon, authenticated;
grant select on public.cart_ticket_items to authenticated;
grant select, insert, update, delete on public.cart_ticket_items to service_role;

-- ---------------------------------------------------------------------------
-- 2. checkout_ticket_holds (service role only)
-- ---------------------------------------------------------------------------

create table if not exists public.checkout_ticket_holds (
  id uuid primary key default gen_random_uuid(),
  checkout_group_id uuid not null references public.checkout_groups (id) on delete cascade,
  cart_ticket_item_id uuid not null,
  ticket_type_id uuid not null references public.ticket_types (id) on delete restrict,
  instance_id uuid not null references public.event_instances (id) on delete restrict,
  event_id uuid not null references public.events (id) on delete restrict,
  organiser_vendor_id uuid not null references public.vendors (id) on delete restrict,
  qty integer not null,
  ticket_ids uuid[] not null,
  status text not null default 'held',
  order_id uuid references public.orders (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint checkout_ticket_holds_qty_check check (qty between 1 and 20),
  constraint checkout_ticket_holds_ids_check check (cardinality(ticket_ids) = qty),
  constraint checkout_ticket_holds_status_check
    check (status in ('held', 'consumed', 'released')),
  constraint checkout_ticket_holds_consumed_check
    check ((status = 'consumed') = (order_id is not null)),
  constraint checkout_ticket_holds_line_key
    unique (checkout_group_id, ticket_type_id, instance_id)
);

create index if not exists checkout_ticket_holds_group_idx
  on public.checkout_ticket_holds (checkout_group_id) where status = 'held';

drop trigger if exists checkout_ticket_holds_set_updated_at on public.checkout_ticket_holds;
create trigger checkout_ticket_holds_set_updated_at
  before update on public.checkout_ticket_holds
  for each row execute function public.set_updated_at();

comment on table public.checkout_ticket_holds is
  'Ticket capacity claimed for a unified checkout session; consumed once by order '
  'placement (ids copied to the ticket order commission snapshot). Service role only.';

alter table public.checkout_ticket_holds enable row level security;
alter table public.checkout_ticket_holds force row level security;
revoke all on public.checkout_ticket_holds from public, anon, authenticated;
grant select, insert, update, delete on public.checkout_ticket_holds to service_role;

-- ---------------------------------------------------------------------------
-- 3. orders.order_lane: one order per vendor per lane in a checkout group
-- ---------------------------------------------------------------------------

alter table public.orders
  add column if not exists order_lane text not null default 'goods';

alter table public.orders drop constraint if exists orders_order_lane_check;
alter table public.orders add constraint orders_order_lane_check
  check (order_lane in ('goods', 'ticket'));

comment on column public.orders.order_lane is
  'goods = products (and legacy single-kind orders); ticket = event tickets bought in a '
  'unified checkout. Kinds never share an order: escrow, settlement and refunds differ.';

create unique index if not exists orders_checkout_group_vendor_lane_key
  on public.orders (checkout_group_id, vendor_id, order_lane);

-- The lane-aware index above is the same idempotency backstop (0031) with the
-- lane added; it exists before the narrower one is dropped.
drop index if exists public.orders_checkout_group_vendor_key;
