-- R02 — user saves for products and events (D37 social commerce).
--
-- Complements product-only `user_wishlist` (0066) with a polymorphic save row
-- for catalogue products and events. `user_wishlist` is NOT migrated or dropped
-- (additive-only convention). Existence of saved entities is validated in the
-- service layer when API endpoints ship; RLS keeps rows owner-scoped.

create table if not exists public.user_saves (
  user_id uuid not null references auth.users (id) on delete cascade,
  entity_kind text not null check (entity_kind in ('product', 'event')),
  entity_id uuid not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (user_id, entity_kind, entity_id)
);

comment on table public.user_saves is
  'Per-user saved products and events (D37). Polymorphic entity_id — validated in API, not FK-constrained.';

create index if not exists user_saves_user_id_created_at_idx
  on public.user_saves (user_id, created_at desc);

create index if not exists user_saves_entity_idx
  on public.user_saves (entity_kind, entity_id);

alter table public.user_saves enable row level security;
alter table public.user_saves force row level security;

drop policy if exists user_saves_owner_select on public.user_saves;
create policy user_saves_owner_select
  on public.user_saves
  for select
  to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists user_saves_owner_insert on public.user_saves;
create policy user_saves_owner_insert
  on public.user_saves
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

drop policy if exists user_saves_owner_delete on public.user_saves;
create policy user_saves_owner_delete
  on public.user_saves
  for delete
  to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists user_saves_admin_all on public.user_saves;
create policy user_saves_admin_all
  on public.user_saves
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy user_saves_owner_select on public.user_saves is
  'A user sees only their own saves. No UPDATE policy — saves are insert/delete only.';

revoke all on public.user_saves from anon, authenticated;
grant select, insert, delete on public.user_saves to authenticated, service_role;
