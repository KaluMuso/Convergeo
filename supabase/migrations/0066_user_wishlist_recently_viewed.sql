-- User engagement: server-side wishlist + recently viewed (cross-device).
-- Additive; reversible via DROP TABLE.

create table public.user_wishlist (
  user_id uuid not null references auth.users (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, product_id)
);

create index user_wishlist_user_id_created_at_idx
  on public.user_wishlist (user_id, created_at desc);

create table public.user_recently_viewed (
  user_id uuid not null references auth.users (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  viewed_at timestamptz not null default now(),
  primary key (user_id, product_id)
);

create index user_recently_viewed_user_id_viewed_at_idx
  on public.user_recently_viewed (user_id, viewed_at desc);

alter table public.user_wishlist enable row level security;
alter table public.user_wishlist force row level security;
alter table public.user_recently_viewed enable row level security;
alter table public.user_recently_viewed force row level security;

-- Wishlist: owner CRUD; admin all.
create policy user_wishlist_owner_select
  on public.user_wishlist
  for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy user_wishlist_owner_insert
  on public.user_wishlist
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

create policy user_wishlist_owner_delete
  on public.user_wishlist
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

create policy user_wishlist_admin_all
  on public.user_wishlist
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Recently viewed: owner CRUD; admin all.
create policy user_recently_viewed_owner_select
  on public.user_recently_viewed
  for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy user_recently_viewed_owner_insert
  on public.user_recently_viewed
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

create policy user_recently_viewed_owner_update
  on public.user_recently_viewed
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy user_recently_viewed_owner_delete
  on public.user_recently_viewed
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

create policy user_recently_viewed_admin_all
  on public.user_recently_viewed
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on table public.user_wishlist is
  'Per-user saved products (server sync for signed-in customers).';
comment on table public.user_recently_viewed is
  'Per-user recently viewed products (capped in application layer).';

grant select, insert, delete on table public.user_wishlist
  to authenticated, service_role;
grant select, insert, update, delete on table public.user_recently_viewed
  to authenticated, service_role;
