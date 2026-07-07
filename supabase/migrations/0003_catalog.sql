-- M03-P02: Catalog schema — categories, canonical products, vendor listings, listing images.

-- ---------------------------------------------------------------------------
-- Validation helpers
-- ---------------------------------------------------------------------------

-- price_tiers shape: [{min_qty int, price_ngwee bigint}] — rejected at insert/update.
create or replace function public.is_valid_price_tiers(tiers jsonb)
returns boolean
language sql
immutable
as $$
  select tiers is null
    or (
      jsonb_typeof(tiers) = 'array'
      and not exists (
        select 1
        from jsonb_array_elements(tiers) as elem
        where jsonb_typeof(elem) <> 'object'
          or not (elem ? 'min_qty' and elem ? 'price_ngwee')
          or jsonb_typeof(elem -> 'min_qty') <> 'number'
          or jsonb_typeof(elem -> 'price_ngwee') <> 'number'
          or (elem ->> 'min_qty') !~ '^[0-9]+$'
          or (elem ->> 'price_ngwee') !~ '^[0-9]+$'
          or (elem ->> 'min_qty')::int < 1
          or (elem ->> 'price_ngwee')::bigint <= 0
      )
    );
$$;

comment on function public.is_valid_price_tiers(jsonb) is
  'Validates B2B price_tiers jsonb: array of {min_qty, price_ngwee} with positive ints.';

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.categories (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid references public.categories (id) on delete restrict,
  name text not null,
  slug text not null unique,
  path text not null,
  -- commission_key values must match commission_rates.category_key (0008_config.sql); no FK across pebbles.
  commission_key text not null,
  vat_flag boolean not null default false,
  prohibited boolean not null default false,
  position integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index categories_parent_id_idx on public.categories (parent_id);
create index categories_path_idx on public.categories (path text_pattern_ops);

create trigger categories_set_updated_at
  before update on public.categories
  for each row
  execute function public.set_updated_at();

comment on column public.categories.commission_key is
  'Logical FK to commission_rates.category_key (seeded in 0008); must stay in sync operationally.';

create table public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  brand text,
  spec jsonb not null default '{}'::jsonb,
  category_id uuid not null references public.categories (id) on delete restrict,
  aliases text[] not null default '{}',
  status text not null default 'pending_moderation'
    check (status in ('pending_moderation', 'active', 'merged')),
  merged_into_id uuid references public.products (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index products_category_id_idx on public.products (category_id);
create index products_status_idx on public.products (status);

create trigger products_set_updated_at
  before update on public.products
  for each row
  execute function public.set_updated_at();

create table public.vendor_listings (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  product_id uuid references public.products (id) on delete set null,
  title_override text,
  price_ngwee bigint not null check (price_ngwee > 0),
  condition text not null check (condition in ('new', 'refurbished')),
  stock_mode text not null check (stock_mode in ('tracked', 'always_available')),
  stock_qty integer check (stock_qty is null or stock_qty >= 0),
  wholesale boolean not null default false,
  price_tiers jsonb check (public.is_valid_price_tiers(price_tiers)),
  moq integer not null default 1 check (moq >= 1),
  returnable boolean not null default false,
  return_window_hours integer,
  status text not null default 'draft'
    check (status in ('draft', 'active', 'paused', 'removed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index vendor_listings_vendor_id_idx on public.vendor_listings (vendor_id);
create index vendor_listings_product_id_idx on public.vendor_listings (product_id);
create index vendor_listings_status_wholesale_idx on public.vendor_listings (status, wholesale);
create index vendor_listings_product_id_active_idx
  on public.vendor_listings (product_id)
  where status = 'active';

create trigger vendor_listings_set_updated_at
  before update on public.vendor_listings
  for each row
  execute function public.set_updated_at();

-- Owners may draft↔active↔paused; removed is admin-only (mirrors 0002 vendor status guard).
create or replace function public.guard_vendor_listing_status_update()
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

  if new.status is distinct from old.status and new.status = 'removed' then
    raise exception 'listing status removed is admin-only';
  end if;

  return new;
end;
$$;

create trigger vendor_listings_guard_status_update
  before update on public.vendor_listings
  for each row
  execute function public.guard_vendor_listing_status_update();

create table public.listing_images (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  cloudinary_public_id text not null,
  position integer not null check (position between 1 and 8),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint listing_images_listing_id_position_key unique (listing_id, position)
);

create index listing_images_listing_id_idx on public.listing_images (listing_id);

create trigger listing_images_set_updated_at
  before update on public.listing_images
  for each row
  execute function public.set_updated_at();

-- Position uniqueness covers slot collisions; count trigger enforces the hard ≤8 cap (M12 contract).
create or replace function public.guard_listing_image_count()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  image_count integer;
begin
  select count(*)::integer
  into image_count
  from public.listing_images
  where listing_id = new.listing_id;

  if image_count >= 8 then
    raise exception 'listing cannot have more than 8 images';
  end if;

  return new;
end;
$$;

create trigger listing_images_guard_count
  before insert on public.listing_images
  for each row
  execute function public.guard_listing_image_count();

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.categories enable row level security;
alter table public.products enable row level security;
alter table public.vendor_listings enable row level security;
alter table public.listing_images enable row level security;

alter table public.categories force row level security;
alter table public.products force row level security;
alter table public.vendor_listings force row level security;
alter table public.listing_images force row level security;

-- categories: public read; admin write.
create policy categories_public_select
  on public.categories
  for select
  using (true);

comment on policy categories_public_select on public.categories is
  'Category tree is publicly readable for navigation and PLP filters.';

create policy categories_admin_insert
  on public.categories
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy categories_admin_update
  on public.categories
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy categories_admin_delete
  on public.categories
  for delete
  to authenticated
  using (public.has_role('admin'));

comment on policy categories_admin_insert on public.categories is
  'Only platform admins may create categories.';
comment on policy categories_admin_update on public.categories is
  'Only platform admins may update categories.';
comment on policy categories_admin_delete on public.categories is
  'Only platform admins may delete categories.';

-- products: public read active only; authenticated insert pinned to pending_moderation; admin all.
create policy products_public_active_select
  on public.products
  for select
  using (status = 'active');

comment on policy products_public_active_select on public.products is
  'Only moderated active canonical products are publicly visible.';

create policy products_authenticated_insert_pending
  on public.products
  for insert
  to authenticated
  with check (status = 'pending_moderation');

comment on policy products_authenticated_insert_pending on public.products is
  'Authenticated users may propose canonical products; status is pinned to pending_moderation.';

create policy products_admin_all
  on public.products
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy products_admin_all on public.products is
  'Platform admins may read, moderate, merge, and delete canonical products.';

-- vendor_listings: public active + active vendor; owner CRUD; admin all.
create policy vendor_listings_public_active_select
  on public.vendor_listings
  for select
  using (
    status = 'active'
    and exists (
      select 1
      from public.vendors v
      where v.id = vendor_listings.vendor_id
        and v.status = 'active'
    )
  );

comment on policy vendor_listings_public_active_select on public.vendor_listings is
  'Active listings are public only when the parent vendor storefront is active.';

create policy vendor_listings_owner_select
  on public.vendor_listings
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_listings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy vendor_listings_owner_select on public.vendor_listings is
  'Owners may read their listings in any lifecycle status.';

create policy vendor_listings_owner_insert
  on public.vendor_listings
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_listings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy vendor_listings_owner_update
  on public.vendor_listings
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_listings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_listings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy vendor_listings_owner_delete
  on public.vendor_listings
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_listings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy vendor_listings_owner_insert on public.vendor_listings is
  'Owners may create listings for vendors they own.';
comment on policy vendor_listings_owner_update on public.vendor_listings is
  'Owners may update their listings; status=removed blocked by trigger.';
comment on policy vendor_listings_owner_delete on public.vendor_listings is
  'Owners may delete their own listings.';

create policy vendor_listings_admin_all
  on public.vendor_listings
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy vendor_listings_admin_all on public.vendor_listings is
  'Platform admins may manage every vendor listing including removal.';

-- listing_images: visibility and ownership follow parent listing.
create policy listing_images_public_active_select
  on public.listing_images
  for select
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_images.listing_id
        and vl.status = 'active'
        and v.status = 'active'
    )
  );

comment on policy listing_images_public_active_select on public.listing_images is
  'Images are public only for active listings on active vendor storefronts.';

create policy listing_images_owner_select
  on public.listing_images
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_images.listing_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy listing_images_owner_insert
  on public.listing_images
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_images.listing_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy listing_images_owner_update
  on public.listing_images
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_images.listing_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_images.listing_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy listing_images_owner_delete
  on public.listing_images
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_images.listing_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy listing_images_owner_select on public.listing_images is
  'Owners may read images for their listings regardless of publish status.';
comment on policy listing_images_owner_insert on public.listing_images is
  'Owners may attach images to listings they own (≤8 enforced by trigger).';
comment on policy listing_images_owner_update on public.listing_images is
  'Owners may reorder or replace images on their listings.';
comment on policy listing_images_owner_delete on public.listing_images is
  'Owners may remove images from their listings.';

create policy listing_images_admin_all
  on public.listing_images
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy listing_images_admin_all on public.listing_images is
  'Platform admins may manage all listing images.';

-- ---------------------------------------------------------------------------
-- Data API grants (auto_expose_new_tables is off in config.toml)
-- ---------------------------------------------------------------------------

grant select on table public.categories to anon, authenticated;
grant select, insert, update, delete on table public.categories to authenticated, service_role;

grant select on table public.products to anon, authenticated;
grant insert on table public.products to authenticated;
grant select, insert, update, delete on table public.products to service_role;

grant select on table public.vendor_listings to anon, authenticated;
grant select, insert, update, delete on table public.vendor_listings to authenticated, service_role;

grant select on table public.listing_images to anon, authenticated;
grant select, insert, update, delete on table public.listing_images to authenticated, service_role;

grant execute on function public.is_valid_price_tiers(jsonb) to authenticated, anon, service_role;
