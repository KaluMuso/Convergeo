-- Service & vendor category taxonomy (Convergeo Strategy Brief §5, pp.86–94).
-- Verticals → sub-categories for RFQ/browse; structural seed only (no vendors/products).
--
-- Down (reversible):
--   drop table if exists public.service_categories;

create table public.service_categories (
  slug text primary key,
  parent_slug text references public.service_categories (slug) on delete restrict,
  name text not null,
  path text not null,
  archetype text,
  regulator text,
  sort int not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index service_categories_parent_slug_idx on public.service_categories (parent_slug);
create index service_categories_path_idx on public.service_categories (path text_pattern_ops);
create index service_categories_is_active_idx on public.service_categories (is_active)
  where is_active = true;

create trigger service_categories_set_updated_at
  before update on public.service_categories
  for each row
  execute function public.set_updated_at();

comment on table public.service_categories is
  'Convergeo service/vendor taxonomy (~110 sub-categories / 14+ verticals). Seeded via scripts/seed_taxonomy.py.';

comment on column public.service_categories.archetype is
  'Dominant transaction archetype from Strategy Brief §3.1 (bookable, quote, buy-now, etc.).';
comment on column public.service_categories.regulator is
  'Tier-2 verification regulator when applicable (HPCZ, ZAMRA, RTSA, …).';

-- ---------------------------------------------------------------------------
-- Row level security (taxonomy is public-read, admin-managed)
-- ---------------------------------------------------------------------------

alter table public.service_categories enable row level security;
alter table public.service_categories force row level security;

create policy service_categories_public_read
  on public.service_categories
  for select
  using (true);

comment on policy service_categories_public_read on public.service_categories is
  'Anyone may read the service category taxonomy.';

create policy service_categories_admin_all
  on public.service_categories
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy service_categories_admin_all on public.service_categories is
  'Platform admins may manage the service category taxonomy.';

grant select on table public.service_categories to anon, authenticated, service_role;
grant insert, update, delete on table public.service_categories to service_role;
