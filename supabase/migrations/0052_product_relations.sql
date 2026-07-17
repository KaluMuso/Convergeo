-- 0052: Curated related-products.
--
-- The PDP "More in this category" rail currently derives related products from
-- the shared category (0045-era logic). This adds an admin-curated override: a
-- product can be given a hand-picked, ordered set of related products, which the
-- PDP prefers over the category fallback.
--
-- product_relations(product_id → related_product_id) with an explicit position
-- for ordering. ON DELETE CASCADE keeps it clean when either product is removed;
-- a CHECK forbids relating a product to itself. Additive; reversible (drop table).
--
-- RLS: public read (relations are catalog metadata; each related product's own
-- active/shoppable status is still enforced when the rail is built) + admin write,
-- mirroring the products/categories policies.

create table if not exists public.product_relations (
  product_id uuid not null references public.products (id) on delete cascade,
  related_product_id uuid not null references public.products (id) on delete cascade,
  position int not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (product_id, related_product_id),
  constraint product_relations_no_self check (product_id <> related_product_id)
);

create index if not exists product_relations_product_id_idx
  on public.product_relations (product_id, position);

alter table public.product_relations enable row level security;

drop policy if exists product_relations_public_select on public.product_relations;
create policy product_relations_public_select on public.product_relations
  for select
  using (true);

drop policy if exists product_relations_admin_all on public.product_relations;
create policy product_relations_admin_all on public.product_relations
  for all
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on table public.product_relations is
  'Admin-curated related products (ordered). PDP prefers these over the category fallback.';
