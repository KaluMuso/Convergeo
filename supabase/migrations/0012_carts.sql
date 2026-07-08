-- M07-P01: Guest + authenticated shopping carts (items only — no stock reservations).

-- ---------------------------------------------------------------------------
-- Helper: guest cart token from request GUC (set by API for guest-scoped queries)
-- ---------------------------------------------------------------------------
create or replace function public.cart_guest_token()
returns text
language sql
stable
as $$
  select nullif(current_setting('request.cart_guest_token', true), '');
$$;

comment on function public.cart_guest_token() is
  'Returns the guest cart token from request.cart_guest_token GUC; empty when unset.';

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table public.carts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users (id) on delete cascade,
  guest_token text,
  status text not null default 'active'
    check (status in ('active', 'converted', 'abandoned')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint carts_owner_check check (user_id is not null or guest_token is not null)
);

create index carts_user_id_idx on public.carts (user_id);
create index carts_guest_token_idx on public.carts (guest_token);

create unique index carts_user_id_active_idx
  on public.carts (user_id)
  where status = 'active' and user_id is not null;

create unique index carts_guest_token_active_idx
  on public.carts (guest_token)
  where status = 'active' and guest_token is not null;

create trigger carts_set_updated_at
  before update on public.carts
  for each row
  execute function public.set_updated_at();

comment on table public.carts is
  'Active shopping carts for authenticated users or signed guest tokens; merge-on-login in M07-P01 API.';

create table public.cart_items (
  id uuid primary key default gen_random_uuid(),
  cart_id uuid not null references public.carts (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete restrict,
  qty integer not null check (qty > 0),
  unit_price_ngwee bigint not null check (unit_price_ngwee > 0),
  wholesale boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint cart_items_cart_id_listing_id_key unique (cart_id, listing_id)
);

create index cart_items_cart_id_idx on public.cart_items (cart_id);
create index cart_items_listing_id_idx on public.cart_items (listing_id);

create trigger cart_items_set_updated_at
  before update on public.cart_items
  for each row
  execute function public.set_updated_at();

comment on table public.cart_items is
  'Cart line items; unit_price_ngwee is server-snapshotted at add/update time.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------
alter table public.carts enable row level security;
alter table public.cart_items enable row level security;

alter table public.carts force row level security;
alter table public.cart_items force row level security;

-- carts: authenticated owner OR guest token match via request GUC.
create policy carts_owner_select
  on public.carts
  for select
  to authenticated
  using (user_id = (select auth.uid()));

comment on policy carts_owner_select on public.carts is
  'Authenticated users may read their own carts.';

create policy carts_guest_select
  on public.carts
  for select
  to authenticated, anon
  using (
    guest_token is not null
    and guest_token = public.cart_guest_token()
  );

comment on policy carts_guest_select on public.carts is
  'Guest carts readable when request.cart_guest_token matches the row guest_token.';

create policy carts_owner_insert
  on public.carts
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

comment on policy carts_owner_insert on public.carts is
  'Authenticated users may create carts owned by themselves.';

create policy carts_guest_insert
  on public.carts
  for insert
  to authenticated, anon
  with check (
    guest_token is not null
    and guest_token = public.cart_guest_token()
    and user_id is null
  );

comment on policy carts_guest_insert on public.carts is
  'Guest carts insertable when guest_token matches request.cart_guest_token.';

create policy carts_owner_update
  on public.carts
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

comment on policy carts_owner_update on public.carts is
  'Authenticated users may update their own carts.';

create policy carts_guest_update
  on public.carts
  for update
  to authenticated, anon
  using (
    guest_token is not null
    and guest_token = public.cart_guest_token()
  )
  with check (
    guest_token is not null
    and guest_token = public.cart_guest_token()
    and user_id is null
  );

comment on policy carts_guest_update on public.carts is
  'Guest carts updatable when guest_token matches request.cart_guest_token.';

create policy carts_owner_delete
  on public.carts
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

comment on policy carts_owner_delete on public.carts is
  'Authenticated users may delete their own carts.';

create policy carts_guest_delete
  on public.carts
  for delete
  to authenticated, anon
  using (
    guest_token is not null
    and guest_token = public.cart_guest_token()
  );

comment on policy carts_guest_delete on public.carts is
  'Guest carts deletable when guest_token matches request.cart_guest_token.';

create policy carts_admin_all
  on public.carts
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy carts_admin_all on public.carts is
  'Platform admins may manage all carts.';

-- cart_items: visibility and mutation follow parent cart ownership.
create policy cart_items_owner_select
  on public.cart_items
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.user_id = (select auth.uid())
    )
  );

comment on policy cart_items_owner_select on public.cart_items is
  'Users may read line items on carts they own.';

create policy cart_items_guest_select
  on public.cart_items
  for select
  to authenticated, anon
  using (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.guest_token is not null
        and c.guest_token = public.cart_guest_token()
    )
  );

comment on policy cart_items_guest_select on public.cart_items is
  'Guest line items readable when parent cart guest_token matches request.cart_guest_token.';

create policy cart_items_owner_insert
  on public.cart_items
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.user_id = (select auth.uid())
    )
  );

comment on policy cart_items_owner_insert on public.cart_items is
  'Users may add line items to carts they own.';

create policy cart_items_guest_insert
  on public.cart_items
  for insert
  to authenticated, anon
  with check (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.guest_token is not null
        and c.guest_token = public.cart_guest_token()
    )
  );

comment on policy cart_items_guest_insert on public.cart_items is
  'Guest line items insertable when parent cart guest_token matches request.cart_guest_token.';

create policy cart_items_owner_update
  on public.cart_items
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.user_id = (select auth.uid())
    )
  );

comment on policy cart_items_owner_update on public.cart_items is
  'Users may update line items on carts they own.';

create policy cart_items_guest_update
  on public.cart_items
  for update
  to authenticated, anon
  using (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.guest_token is not null
        and c.guest_token = public.cart_guest_token()
    )
  )
  with check (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.guest_token is not null
        and c.guest_token = public.cart_guest_token()
    )
  );

comment on policy cart_items_guest_update on public.cart_items is
  'Guest line items updatable when parent cart guest_token matches request.cart_guest_token.';

create policy cart_items_owner_delete
  on public.cart_items
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.user_id = (select auth.uid())
    )
  );

comment on policy cart_items_owner_delete on public.cart_items is
  'Users may remove line items from carts they own.';

create policy cart_items_guest_delete
  on public.cart_items
  for delete
  to authenticated, anon
  using (
    exists (
      select 1
      from public.carts c
      where c.id = cart_items.cart_id
        and c.guest_token is not null
        and c.guest_token = public.cart_guest_token()
    )
  );

comment on policy cart_items_guest_delete on public.cart_items is
  'Guest line items deletable when parent cart guest_token matches request.cart_guest_token.';

create policy cart_items_admin_all
  on public.cart_items
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy cart_items_admin_all on public.cart_items is
  'Platform admins may manage all cart line items.';

-- ---------------------------------------------------------------------------
-- API grants
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on table public.carts to authenticated, anon, service_role;
grant select, insert, update, delete on table public.cart_items to authenticated, anon, service_role;

grant execute on function public.cart_guest_token() to authenticated, anon, service_role;
