-- M03-P04: Orders spine & reservations — checkout groups, orders, line items, stock holds, audit.
-- Completes tickets.order_item_id FK from 0004_services_events.sql.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.addresses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  label text,
  landmark text not null,
  lat double precision,
  lng double precision,
  phone text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index addresses_user_id_idx on public.addresses (user_id);

create trigger addresses_set_updated_at
  before update on public.addresses
  for each row
  execute function public.set_updated_at();

create table public.checkout_groups (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references auth.users (id) on delete restrict,
  idempotency_key text not null unique,
  subtotal_ngwee bigint not null check (subtotal_ngwee >= 0),
  delivery_fee_ngwee bigint not null check (delivery_fee_ngwee >= 0),
  total_ngwee bigint not null check (total_ngwee >= 0),
  status text not null default 'pending'
    check (status in ('pending', 'completed', 'abandoned', 'expired')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index checkout_groups_customer_id_idx on public.checkout_groups (customer_id);

create trigger checkout_groups_set_updated_at
  before update on public.checkout_groups
  for each row
  execute function public.set_updated_at();

comment on table public.checkout_groups is
  'One customer checkout may fan out to N vendor orders; totals and idempotency_key are server-computed — no client insert/update policies.';

create table public.orders (
  id uuid primary key default gen_random_uuid(),
  checkout_group_id uuid not null references public.checkout_groups (id) on delete restrict,
  vendor_id uuid not null references public.vendors (id) on delete restrict,
  customer_id uuid not null references auth.users (id) on delete restrict,
  status text not null default 'placed'
    check (status in (
      'placed', 'confirmed', 'processing', 'ready',
      'shipped', 'delivered', 'completed', 'cancelled'
    )),
  fulfilment text not null check (fulfilment in ('delivery', 'pickup')),
  delivery_zone text,
  address_id uuid references public.addresses (id) on delete set null,
  delivery_fee_ngwee bigint not null default 0 check (delivery_fee_ngwee >= 0),
  cod boolean not null default false,
  commission_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index orders_vendor_id_status_idx on public.orders (vendor_id, status);
create index orders_customer_id_created_at_idx on public.orders (customer_id, created_at desc);
create index orders_checkout_group_id_idx on public.orders (checkout_group_id);

create trigger orders_set_updated_at
  before update on public.orders
  for each row
  execute function public.set_updated_at();

create table public.order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete cascade,
  item_kind text not null
    check (item_kind in ('product', 'ticket', 'service_deposit', 'service_balance')),
  qty int not null check (qty > 0),
  unit_price_ngwee bigint not null check (unit_price_ngwee > 0),
  title_snapshot text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index order_items_order_id_idx on public.order_items (order_id);

create trigger order_items_set_updated_at
  before update on public.order_items
  for each row
  execute function public.set_updated_at();

create table public.order_item_products (
  order_item_id uuid primary key references public.order_items (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete restrict,
  product_id uuid references public.products (id) on delete set null
);

create table public.order_item_tickets (
  order_item_id uuid primary key references public.order_items (id) on delete cascade,
  ticket_type_id uuid not null references public.ticket_types (id) on delete restrict,
  instance_id uuid not null references public.event_instances (id) on delete restrict
);

create table public.order_item_services (
  order_item_id uuid primary key references public.order_items (id) on delete cascade,
  job_id uuid references public.jobs (id) on delete set null,
  quote_id uuid references public.job_quotes (id) on delete set null
);

-- Complete 0004 contract: tickets.order_item_id → order_items.
alter table public.tickets
  add constraint tickets_order_item_id_fkey
  foreign key (order_item_id) references public.order_items (id);

create table public.stock_reservations (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  checkout_group_id uuid not null references public.checkout_groups (id) on delete cascade,
  qty int not null check (qty > 0),
  expires_at timestamptz not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint stock_reservations_listing_id_checkout_group_id_key
    unique (listing_id, checkout_group_id)
);

create index stock_reservations_expires_at_idx on public.stock_reservations (expires_at);

create trigger stock_reservations_set_updated_at
  before update on public.stock_reservations
  for each row
  execute function public.set_updated_at();

create table public.order_events (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete cascade,
  actor uuid,
  from_status text,
  to_status text,
  note text,
  created_at timestamptz not null default timezone('utc', now())
);

create index order_events_order_id_created_at_idx
  on public.order_events (order_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Guard + audit triggers
-- ---------------------------------------------------------------------------

-- Status transitions are server-controlled (M09 state machine); clients may not flip status.
create or replace function public.guard_orders_status_update()
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

  if new.status is distinct from old.status then
    raise exception 'order status is server-controlled';
  end if;

  return new;
end;
$$;

create trigger orders_guard_status_update
  before update on public.orders
  for each row
  execute function public.guard_orders_status_update();

-- Append-only audit row on every status change (security definer bypasses FORCE RLS).
create or replace function public.audit_orders_status_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    insert into public.order_events (order_id, actor, from_status, to_status)
    values (new.id, auth.uid(), old.status, new.status);
  end if;

  return new;
end;
$$;

create trigger orders_audit_status_change
  after update on public.orders
  for each row
  execute function public.audit_orders_status_change();

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.addresses enable row level security;
alter table public.checkout_groups enable row level security;
alter table public.orders enable row level security;
alter table public.order_items enable row level security;
alter table public.order_item_products enable row level security;
alter table public.order_item_tickets enable row level security;
alter table public.order_item_services enable row level security;
alter table public.stock_reservations enable row level security;
alter table public.order_events enable row level security;

alter table public.addresses force row level security;
alter table public.checkout_groups force row level security;
alter table public.orders force row level security;
alter table public.order_items force row level security;
alter table public.order_item_products force row level security;
alter table public.order_item_tickets force row level security;
alter table public.order_item_services force row level security;
alter table public.stock_reservations force row level security;
alter table public.order_events force row level security;

-- addresses: owner CRUD own; admin all.
create policy addresses_owner_select
  on public.addresses
  for select
  to authenticated
  using (user_id = (select auth.uid()));

comment on policy addresses_owner_select on public.addresses is
  'Users may read their own saved delivery addresses.';

create policy addresses_owner_insert
  on public.addresses
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

create policy addresses_owner_update
  on public.addresses
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy addresses_owner_delete
  on public.addresses
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

comment on policy addresses_owner_insert on public.addresses is
  'Users may create addresses for themselves.';
comment on policy addresses_owner_update on public.addresses is
  'Users may update their own addresses.';
comment on policy addresses_owner_delete on public.addresses is
  'Users may delete their own addresses.';

create policy addresses_admin_all
  on public.addresses
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy addresses_admin_all on public.addresses is
  'Platform admins may manage every address row.';

-- checkout_groups: customer reads own; server creates/updates (no client write policies).
create policy checkout_groups_customer_select
  on public.checkout_groups
  for select
  to authenticated
  using (customer_id = (select auth.uid()));

comment on policy checkout_groups_customer_select on public.checkout_groups is
  'Customers may read their own checkout sessions; insert/update require service_role (totals/idempotency are server-computed).';

-- orders: customer + vendor read; no client insert/update (status guarded by trigger for any bypass).
create policy orders_customer_select
  on public.orders
  for select
  to authenticated
  using (customer_id = (select auth.uid()));

comment on policy orders_customer_select on public.orders is
  'Customers may read orders they placed.';

create policy orders_vendor_select
  on public.orders
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = orders.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy orders_vendor_select on public.orders is
  'Vendor owners may read orders for their storefront; status changes are server-only.';

create policy orders_admin_all
  on public.orders
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy orders_admin_all on public.orders is
  'Platform admins may read and mutate orders (status still audited).';

-- order_items: visible to parent order customer or vendor; no client writes.
create policy order_items_party_select
  on public.order_items
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.orders o
      where o.id = order_items.order_id
        and (
          o.customer_id = (select auth.uid())
          or exists (
            select 1
            from public.vendors v
            where v.id = o.vendor_id
              and v.owner_user_id = (select auth.uid())
          )
        )
    )
  );

comment on policy order_items_party_select on public.order_items is
  'Order line items visible to the placing customer and fulfilling vendor only; server writes.';

create policy order_items_admin_all
  on public.order_items
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy order_items_admin_all on public.order_items is
  'Platform admins may manage order line items.';

-- Detail tables: same party visibility via parent order_item → order.
create policy order_item_products_party_select
  on public.order_item_products
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.order_items oi
      join public.orders o on o.id = oi.order_id
      where oi.id = order_item_products.order_item_id
        and (
          o.customer_id = (select auth.uid())
          or exists (
            select 1
            from public.vendors v
            where v.id = o.vendor_id
              and v.owner_user_id = (select auth.uid())
          )
        )
    )
  );

comment on policy order_item_products_party_select on public.order_item_products is
  'Product line detail visible to order customer and vendor; server writes.';

create policy order_item_products_admin_all
  on public.order_item_products
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy order_item_tickets_party_select
  on public.order_item_tickets
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.order_items oi
      join public.orders o on o.id = oi.order_id
      where oi.id = order_item_tickets.order_item_id
        and (
          o.customer_id = (select auth.uid())
          or exists (
            select 1
            from public.vendors v
            where v.id = o.vendor_id
              and v.owner_user_id = (select auth.uid())
          )
        )
    )
  );

comment on policy order_item_tickets_party_select on public.order_item_tickets is
  'Ticket line detail visible to order customer and vendor; server writes.';

create policy order_item_tickets_admin_all
  on public.order_item_tickets
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy order_item_services_party_select
  on public.order_item_services
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.order_items oi
      join public.orders o on o.id = oi.order_id
      where oi.id = order_item_services.order_item_id
        and (
          o.customer_id = (select auth.uid())
          or exists (
            select 1
            from public.vendors v
            where v.id = o.vendor_id
              and v.owner_user_id = (select auth.uid())
          )
        )
    )
  );

comment on policy order_item_services_party_select on public.order_item_services is
  'Service line detail visible to order customer and vendor; server writes.';

create policy order_item_services_admin_all
  on public.order_item_services
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- stock_reservations: intentionally zero client policies (server-only).
comment on table public.stock_reservations is
  'Inventory holds during checkout; RLS enabled with zero client policies — service_role only.';

-- order_events: parties on parent order may read; trigger-written only.
create policy order_events_party_select
  on public.order_events
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.orders o
      where o.id = order_events.order_id
        and (
          o.customer_id = (select auth.uid())
          or exists (
            select 1
            from public.vendors v
            where v.id = o.vendor_id
              and v.owner_user_id = (select auth.uid())
          )
        )
    )
  );

comment on policy order_events_party_select on public.order_events is
  'Status audit trail readable by order customer and vendor; rows inserted by audit trigger only.';

create policy order_events_admin_all
  on public.order_events
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- API roles need table privileges; RLS policies enforce authorization.
grant select, insert, update, delete on table public.addresses to authenticated, service_role;
grant select, insert, update, delete on table public.checkout_groups to authenticated, service_role;
grant select, insert, update, delete on table public.orders to authenticated, service_role;
grant select, insert, update, delete on table public.order_items to authenticated, service_role;
grant select, insert, update, delete on table public.order_item_products to authenticated, service_role;
grant select, insert, update, delete on table public.order_item_tickets to authenticated, service_role;
grant select, insert, update, delete on table public.order_item_services to authenticated, service_role;
grant select, insert, update, delete on table public.stock_reservations to authenticated, service_role;
grant select, insert, update, delete on table public.order_events to authenticated, service_role;

grant execute on function public.guard_orders_status_update() to authenticated, service_role;
grant execute on function public.audit_orders_status_change() to authenticated, service_role;
