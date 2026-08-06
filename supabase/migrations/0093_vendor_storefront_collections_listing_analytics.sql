-- R02-P15 — Vendor storefront collections + listing impression/PDP analytics.
--
-- Collections let vendors merchandise their own storefront. Analytics are
-- aggregated per listing per UTC day with dedupe by (session, listing, day, kind).

-- ---------------------------------------------------------------------------
-- vendor_storefront_collections
-- ---------------------------------------------------------------------------
create table if not exists public.vendor_storefront_collections (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  title text not null check (length(btrim(title)) between 1 and 120),
  slug text not null check (slug ~ '^[a-z0-9-]+$'),
  sort_order integer not null default 0 check (sort_order >= 0),
  status text not null default 'active' check (status in ('active', 'draft')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint vendor_storefront_collections_vendor_slug_uniq unique (vendor_id, slug)
);

create index if not exists vendor_storefront_collections_vendor_sort_idx
  on public.vendor_storefront_collections (vendor_id, sort_order, id);

comment on table public.vendor_storefront_collections is
  'Vendor-curated storefront collections. Public when status=active and vendor is active.';

drop trigger if exists vendor_storefront_collections_set_updated_at
  on public.vendor_storefront_collections;
create trigger vendor_storefront_collections_set_updated_at
  before update on public.vendor_storefront_collections
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- vendor_storefront_collection_items
-- ---------------------------------------------------------------------------
create table if not exists public.vendor_storefront_collection_items (
  collection_id uuid not null
    references public.vendor_storefront_collections (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  sort_order integer not null default 0 check (sort_order >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (collection_id, listing_id)
);

create index if not exists vendor_storefront_collection_items_listing_idx
  on public.vendor_storefront_collection_items (listing_id);

comment on table public.vendor_storefront_collection_items is
  'Listings assigned to a vendor storefront collection. Ownership enforced by trigger.';

-- ---------------------------------------------------------------------------
-- Ownership guard — a vendor may only merchandise their own listings.
-- ---------------------------------------------------------------------------
create or replace function public.storefront_collection_items_guard()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  collection_vendor uuid;
  listing_vendor uuid;
begin
  select c.vendor_id into collection_vendor
  from public.vendor_storefront_collections c
  where c.id = new.collection_id;

  if collection_vendor is null then
    raise exception 'collection % does not exist', new.collection_id
      using errcode = 'foreign_key_violation';
  end if;

  select vl.vendor_id into listing_vendor
  from public.vendor_listings vl
  where vl.id = new.listing_id;

  if listing_vendor is null then
    raise exception 'listing % does not exist', new.listing_id
      using errcode = 'foreign_key_violation';
  end if;

  if listing_vendor <> collection_vendor then
    raise exception
      'storefront_collection_items: listing % does not belong to the collection''s vendor',
      new.listing_id
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists storefront_collection_items_guard_trg
  on public.vendor_storefront_collection_items;
create trigger storefront_collection_items_guard_trg
  before insert or update on public.vendor_storefront_collection_items
  for each row execute function public.storefront_collection_items_guard();

comment on function public.storefront_collection_items_guard() is
  'DB-layer enforcement: a collection may only contain listings owned by its vendor.';

-- ---------------------------------------------------------------------------
-- listing_analytics — daily aggregates, partitioned by day (UTC).
-- ---------------------------------------------------------------------------
create table if not exists public.listing_analytics (
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  day date not null,
  impressions bigint not null default 0 check (impressions >= 0),
  pdp_views bigint not null default 0 check (pdp_views >= 0),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (listing_id, day)
) partition by range (day);

comment on table public.listing_analytics is
  'Lightweight per-listing per-day view counters (impressions + PDP views). Partitioned by UTC day.';

-- Initial partitions: trailing 30 days + next 7 days (UTC).
do $$
declare
  d date := (timezone('utc', now()))::date - 30;
  part_name text;
  part_end date;
begin
  while d <= (timezone('utc', now()))::date + 7 loop
    part_end := d + 1;
    part_name := format('listing_analytics_%s', to_char(d, 'YYYY_MM_DD'));
    execute format(
      'create table if not exists public.%I partition of public.listing_analytics
         for values from (%L) to (%L)',
      part_name,
      d,
      part_end
    );
    execute format('alter table public.%I enable row level security', part_name);
    execute format('alter table public.%I force row level security', part_name);
    d := d + 1;
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- listing_view_dedup — idempotent by constraint (session, listing, day, kind).
-- ---------------------------------------------------------------------------
create table if not exists public.listing_view_dedup (
  session_id uuid not null,
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  day date not null,
  view_kind text not null check (view_kind in ('impression', 'pdp_view')),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (session_id, listing_id, day, view_kind)
) partition by range (day);

comment on table public.listing_view_dedup is
  'Dedupes listing impressions/PDP views per viewer session per UTC day.';

do $$
declare
  d date := (timezone('utc', now()))::date - 30;
  part_name text;
  part_end date;
begin
  while d <= (timezone('utc', now()))::date + 7 loop
    part_end := d + 1;
    part_name := format('listing_view_dedup_%s', to_char(d, 'YYYY_MM_DD'));
    execute format(
      'create table if not exists public.%I partition of public.listing_view_dedup
         for values from (%L) to (%L)',
      part_name,
      d,
      part_end
    );
    execute format('alter table public.%I enable row level security', part_name);
    execute format('alter table public.%I force row level security', part_name);
    d := d + 1;
  end loop;
end;
$$;

-- Ensure today's partition exists for late-night deploys.
create or replace function public.ensure_listing_analytics_partition(p_day date)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  part_name text;
  part_end date;
begin
  part_end := p_day + 1;
  part_name := format('listing_analytics_%s', to_char(p_day, 'YYYY_MM_DD'));
  execute format(
    'create table if not exists public.%I partition of public.listing_analytics
       for values from (%L) to (%L)',
    part_name,
    p_day,
    part_end
  );
  execute format('alter table public.%I enable row level security', part_name);
  execute format('alter table public.%I force row level security', part_name);
  part_name := format('listing_view_dedup_%s', to_char(p_day, 'YYYY_MM_DD'));
  execute format(
    'create table if not exists public.%I partition of public.listing_view_dedup
       for values from (%L) to (%L)',
    part_name,
    p_day,
    part_end
  );
  execute format('alter table public.%I enable row level security', part_name);
  execute format('alter table public.%I force row level security', part_name);
end;
$$;

revoke all on function public.ensure_listing_analytics_partition(date) from public;
grant execute on function public.ensure_listing_analytics_partition(date) to service_role;

-- Atomic record: returns 1 when counted, 0 when deduped.
create or replace function public.record_listing_view(
  p_session_id uuid,
  p_listing_id uuid,
  p_day date,
  p_view_kind text
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
begin
  perform public.ensure_listing_analytics_partition(p_day);

  insert into public.listing_view_dedup (session_id, listing_id, day, view_kind)
  values (p_session_id, p_listing_id, p_day, p_view_kind)
  on conflict do nothing;

  if not found then
    return 0;
  end if;

  insert into public.listing_analytics as la (listing_id, day, impressions, pdp_views)
  values (
    p_listing_id,
    p_day,
    case when p_view_kind = 'impression' then 1 else 0 end,
    case when p_view_kind = 'pdp_view' then 1 else 0 end
  )
  on conflict (listing_id, day) do update
    set impressions = la.impressions + excluded.impressions,
        pdp_views = la.pdp_views + excluded.pdp_views,
        updated_at = timezone('utc', now());

  return 1;
end;
$$;

revoke all on function public.record_listing_view(uuid, uuid, date, text) from public;
grant execute on function public.record_listing_view(uuid, uuid, date, text) to service_role;

-- ---------------------------------------------------------------------------
-- RLS — collections
-- ---------------------------------------------------------------------------
alter table public.vendor_storefront_collections enable row level security;
alter table public.vendor_storefront_collections force row level security;

alter table public.vendor_storefront_collection_items enable row level security;
alter table public.vendor_storefront_collection_items force row level security;

drop policy if exists vendor_storefront_collections_public_select
  on public.vendor_storefront_collections;
create policy vendor_storefront_collections_public_select
  on public.vendor_storefront_collections
  for select
  to anon, authenticated
  using (
    status = 'active'
    and exists (
      select 1 from public.vendors v
      where v.id = vendor_storefront_collections.vendor_id
        and v.status = 'active'
    )
  );

drop policy if exists vendor_storefront_collections_owner_all
  on public.vendor_storefront_collections;
create policy vendor_storefront_collections_owner_all
  on public.vendor_storefront_collections
  for all
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = vendor_storefront_collections.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  )
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = vendor_storefront_collections.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  );

drop policy if exists vendor_storefront_collection_items_public_select
  on public.vendor_storefront_collection_items;
create policy vendor_storefront_collection_items_public_select
  on public.vendor_storefront_collection_items
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.vendor_storefront_collections c
      join public.vendors v on v.id = c.vendor_id
      where c.id = vendor_storefront_collection_items.collection_id
        and c.status = 'active'
        and v.status = 'active'
    )
  );

drop policy if exists vendor_storefront_collection_items_owner_all
  on public.vendor_storefront_collection_items;
create policy vendor_storefront_collection_items_owner_all
  on public.vendor_storefront_collection_items
  for all
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_storefront_collections c
      join public.vendors v on v.id = c.vendor_id
      where c.id = vendor_storefront_collection_items.collection_id
        and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  )
  with check (
    exists (
      select 1
      from public.vendor_storefront_collections c
      join public.vendors v on v.id = c.vendor_id
      where c.id = vendor_storefront_collection_items.collection_id
        and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  );

revoke all on public.vendor_storefront_collections from anon, authenticated;
grant select, insert, update, delete on public.vendor_storefront_collections to authenticated;
grant select on public.vendor_storefront_collections to anon;

revoke all on public.vendor_storefront_collection_items from anon, authenticated;
grant select, insert, update, delete on public.vendor_storefront_collection_items to authenticated;
grant select on public.vendor_storefront_collection_items to anon;

-- ---------------------------------------------------------------------------
-- RLS — listing_analytics (vendor reads own listings only; writes service_role)
-- ---------------------------------------------------------------------------
alter table public.listing_analytics enable row level security;
alter table public.listing_analytics force row level security;

alter table public.listing_view_dedup enable row level security;
alter table public.listing_view_dedup force row level security;

drop policy if exists listing_analytics_vendor_select on public.listing_analytics;
create policy listing_analytics_vendor_select
  on public.listing_analytics
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_listings vl
      join public.vendors v on v.id = vl.vendor_id
      where vl.id = listing_analytics.listing_id
        and (v.owner_user_id = (select auth.uid()) or public.has_role('admin'))
    )
  );

drop policy if exists listing_analytics_service_role_all on public.listing_analytics;
create policy listing_analytics_service_role_all
  on public.listing_analytics
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists listing_analytics_admin_select on public.listing_analytics;
create policy listing_analytics_admin_select
  on public.listing_analytics
  for select
  to authenticated
  using (public.has_role('admin'));

drop policy if exists listing_view_dedup_service_role_all on public.listing_view_dedup;
create policy listing_view_dedup_service_role_all
  on public.listing_view_dedup
  for all
  to service_role
  using (true)
  with check (true);

revoke all on public.listing_analytics from anon, authenticated;
grant select on public.listing_analytics to authenticated;

revoke all on public.listing_view_dedup from anon, authenticated;
