-- M03-P08: Unified search projection, sync triggers, RRF search, and synonyms.
-- Feeds M05 search API and M06 "Ask Vergeo" RAG (embedding vector(384) populated later).

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.search_documents (
  id uuid primary key default gen_random_uuid(),
  entity_kind text not null
    check (entity_kind in ('product', 'listing', 'service', 'event', 'vendor')),
  entity_id uuid not null,
  title text not null default '',
  body text not null default '',
  category_path text,
  price_min_ngwee bigint,
  price_max_ngwee bigint,
  lat double precision,
  lng double precision,
  locale_terms text[],
  tsv tsvector generated always as (
    to_tsvector(
      'simple',
      coalesce(title, '') || ' ' || coalesce(body, '') || ' '
        || array_to_string(coalesce(locale_terms, '{}'), ' ')
    )
  ) stored,
  embedding vector(384),
  boost_signals jsonb not null default '{}'::jsonb,
  is_public boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint search_documents_entity_kind_entity_id_key unique (entity_kind, entity_id)
);

create index search_documents_tsv_gin_idx
  on public.search_documents using gin (tsv);

create index search_documents_title_trgm_idx
  on public.search_documents using gin (title gin_trgm_ops);

create index search_documents_embedding_hnsw_idx
  on public.search_documents using hnsw (embedding vector_cosine_ops);

create index search_documents_entity_kind_idx
  on public.search_documents (entity_kind);

create index search_documents_is_public_idx
  on public.search_documents (is_public)
  where is_public = true;

create index search_documents_price_min_ngwee_idx
  on public.search_documents (price_min_ngwee)
  where is_public = true;

create trigger search_documents_set_updated_at
  before update on public.search_documents
  for each row
  execute function public.set_updated_at();

comment on table public.search_documents is
  'Unified search projection for products, listings, services, events, and vendors. Writable only via sync triggers / service_role.';

create table public.synonyms (
  id uuid primary key default gen_random_uuid(),
  term text not null,
  canonical text not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint synonyms_term_canonical_key unique (term, canonical)
);

create index synonyms_term_idx on public.synonyms (term);
create index synonyms_canonical_idx on public.synonyms (canonical);

comment on table public.synonyms is
  'Locale search term variants (Bemba/Nyanja) mapped to canonical spellings for fuzzy + FTS expansion.';

-- ---------------------------------------------------------------------------
-- Synonym seeds (Bemba / Nyanja common variants)
-- ---------------------------------------------------------------------------

insert into public.synonyms (term, canonical) values
  ('chitange', 'chitenge'),
  ('chitengi', 'chitenge'),
  ('chitenje', 'chitenge'),
  ('foni', 'phone'),
  ('fon', 'phone'),
  ('ma foni', 'phone'),
  ('nsapato', 'shoes'),
  ('sapato', 'shoes'),
  ('zikomo', 'thank you'),
  ('muli bwanji', 'hello');

-- ---------------------------------------------------------------------------
-- Sync helpers (security definer, pinned search_path)
-- ---------------------------------------------------------------------------

create or replace function public.search_remove_document(
  p_entity_kind text,
  p_entity_id uuid
)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  delete from public.search_documents
  where entity_kind = p_entity_kind
    and entity_id = p_entity_id;
end;
$$;

create or replace function public.search_mark_unpublished(
  p_entity_kind text,
  p_entity_id uuid
)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  update public.search_documents
  set is_public = false,
      updated_at = timezone('utc', now())
  where entity_kind = p_entity_kind
    and entity_id = p_entity_id;
end;
$$;

-- product: title=name, body=brand+spec keys, category_path from categories.path,
-- locale_terms=aliases; only status='active' is public.
create or replace function public.search_upsert_product(p_product_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
begin
  select
    p.id,
    p.name,
    p.brand,
    p.spec,
    p.aliases,
    p.status,
    c.path as category_path
  into v_row
  from public.products p
  left join public.categories c on c.id = p.category_id
  where p.id = p_product_id;

  if not found then
    perform public.search_remove_document('product', p_product_id);
    return;
  end if;

  if v_row.status <> 'active' then
    perform public.search_mark_unpublished('product', p_product_id);
    return;
  end if;

  insert into public.search_documents (
    entity_kind,
    entity_id,
    title,
    body,
    category_path,
    price_min_ngwee,
    price_max_ngwee,
    lat,
    lng,
    locale_terms,
    boost_signals,
    is_public
  )
  values (
    'product',
    v_row.id,
    v_row.name,
    trim(both ' ' from coalesce(v_row.brand, '') || ' ' || coalesce(v_row.spec::text, '')),
    v_row.category_path,
    null,
    null,
    null,
    null,
    v_row.aliases,
    '{}'::jsonb,
    true
  )
  on conflict (entity_kind, entity_id) do update
  set
    title = excluded.title,
    body = excluded.body,
    category_path = excluded.category_path,
    price_min_ngwee = excluded.price_min_ngwee,
    price_max_ngwee = excluded.price_max_ngwee,
    lat = excluded.lat,
    lng = excluded.lng,
    locale_terms = excluded.locale_terms,
    boost_signals = excluded.boost_signals,
    is_public = true,
    updated_at = timezone('utc', now());
end;
$$;

-- listing: title=title_override|product.name, body=vendor+condition, category_path from product,
-- price from listing, geo from first vendor location, locale_terms=product aliases,
-- boost_signals in_stock/verified; active listing on active vendor only.
create or replace function public.search_upsert_listing(p_listing_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
  v_in_stock boolean;
  v_verified boolean;
begin
  select
    vl.id,
    vl.title_override,
    vl.price_ngwee,
    vl.condition,
    vl.stock_mode,
    vl.stock_qty,
    vl.status as listing_status,
    v.status as vendor_status,
    v.display_name as vendor_name,
    v.kyc_tier,
    v.preferred_badge,
    p.name as product_name,
    p.aliases as product_aliases,
    c.path as category_path,
    loc.lat,
    loc.lng
  into v_row
  from public.vendor_listings vl
  join public.vendors v on v.id = vl.vendor_id
  left join public.products p on p.id = vl.product_id
  left join public.categories c on c.id = p.category_id
  left join lateral (
    select vl2.lat, vl2.lng
    from public.vendor_locations vl2
    where vl2.vendor_id = vl.vendor_id
    order by vl2.created_at
    limit 1
  ) loc on true
  where vl.id = p_listing_id;

  if not found then
    perform public.search_remove_document('listing', p_listing_id);
    return;
  end if;

  if v_row.listing_status <> 'active' or v_row.vendor_status <> 'active' then
    perform public.search_mark_unpublished('listing', p_listing_id);
    return;
  end if;

  v_in_stock := v_row.stock_mode = 'always_available'
    or coalesce(v_row.stock_qty, 0) > 0;
  v_verified := coalesce(v_row.kyc_tier, 0) >= 2 or coalesce(v_row.preferred_badge, false);

  insert into public.search_documents (
    entity_kind,
    entity_id,
    title,
    body,
    category_path,
    price_min_ngwee,
    price_max_ngwee,
    lat,
    lng,
    locale_terms,
    boost_signals,
    is_public
  )
  values (
    'listing',
    v_row.id,
    coalesce(nullif(trim(v_row.title_override), ''), v_row.product_name, 'Listing'),
    trim(both ' ' from coalesce(v_row.vendor_name, '') || ' ' || coalesce(v_row.condition, '')),
    v_row.category_path,
    v_row.price_ngwee,
    v_row.price_ngwee,
    v_row.lat,
    v_row.lng,
    v_row.product_aliases,
    jsonb_build_object(
      'in_stock', v_in_stock,
      'verified', v_verified,
      'below_median', false
    ),
    true
  )
  on conflict (entity_kind, entity_id) do update
  set
    title = excluded.title,
    body = excluded.body,
    category_path = excluded.category_path,
    price_min_ngwee = excluded.price_min_ngwee,
    price_max_ngwee = excluded.price_max_ngwee,
    lat = excluded.lat,
    lng = excluded.lng,
    locale_terms = excluded.locale_terms,
    boost_signals = excluded.boost_signals,
    is_public = true,
    updated_at = timezone('utc', now());
end;
$$;

-- service: title/description, category_path=services.category text, price=from_price_ngwee.
create or replace function public.search_upsert_service(p_service_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
begin
  select
    s.id,
    s.title,
    s.description,
    s.category,
    s.service_area,
    s.from_price_ngwee,
    s.status as service_status,
    v.status as vendor_status,
    v.display_name as vendor_name,
    v.kyc_tier,
    v.preferred_badge,
    loc.lat,
    loc.lng
  into v_row
  from public.services s
  join public.vendors v on v.id = s.vendor_id
  left join lateral (
    select vl.lat, vl.lng
    from public.vendor_locations vl
    where vl.vendor_id = s.vendor_id
    order by vl.created_at
    limit 1
  ) loc on true
  where s.id = p_service_id;

  if not found then
    perform public.search_remove_document('service', p_service_id);
    return;
  end if;

  if v_row.service_status <> 'active' or v_row.vendor_status <> 'active' then
    perform public.search_mark_unpublished('service', p_service_id);
    return;
  end if;

  insert into public.search_documents (
    entity_kind,
    entity_id,
    title,
    body,
    category_path,
    price_min_ngwee,
    price_max_ngwee,
    lat,
    lng,
    locale_terms,
    boost_signals,
    is_public
  )
  values (
    'service',
    v_row.id,
    v_row.title,
    trim(both ' ' from coalesce(v_row.description, '') || ' ' || coalesce(v_row.service_area, '') || ' ' || coalesce(v_row.vendor_name, '')),
    v_row.category,
    v_row.from_price_ngwee,
    v_row.from_price_ngwee,
    v_row.lat,
    v_row.lng,
    null,
    jsonb_build_object(
      'in_stock', true,
      'verified', coalesce(v_row.kyc_tier, 0) >= 2 or coalesce(v_row.preferred_badge, false),
      'below_median', false
    ),
    true
  )
  on conflict (entity_kind, entity_id) do update
  set
    title = excluded.title,
    body = excluded.body,
    category_path = excluded.category_path,
    price_min_ngwee = excluded.price_min_ngwee,
    price_max_ngwee = excluded.price_max_ngwee,
    lat = excluded.lat,
    lng = excluded.lng,
    locale_terms = excluded.locale_terms,
    boost_signals = excluded.boost_signals,
    is_public = true,
    updated_at = timezone('utc', now());
end;
$$;

-- event: title/description, geo from event lat/lng, price min/max from ticket_types.
create or replace function public.search_upsert_event(p_event_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
  v_price_min bigint;
  v_price_max bigint;
begin
  select
    e.id,
    e.title,
    e.description,
    e.venue,
    e.lat,
    e.lng,
    e.status as event_status,
    v.status as vendor_status,
    v.display_name as vendor_name
  into v_row
  from public.events e
  join public.vendors v on v.id = e.organiser_vendor_id
  where e.id = p_event_id;

  if not found then
    perform public.search_remove_document('event', p_event_id);
    return;
  end if;

  if v_row.event_status <> 'published' or v_row.vendor_status <> 'active' then
    perform public.search_mark_unpublished('event', p_event_id);
    return;
  end if;

  select min(tt.price_ngwee), max(tt.price_ngwee)
  into v_price_min, v_price_max
  from public.ticket_types tt
  where tt.event_id = p_event_id;

  insert into public.search_documents (
    entity_kind,
    entity_id,
    title,
    body,
    category_path,
    price_min_ngwee,
    price_max_ngwee,
    lat,
    lng,
    locale_terms,
    boost_signals,
    is_public
  )
  values (
    'event',
    v_row.id,
    v_row.title,
    trim(both ' ' from coalesce(v_row.description, '') || ' ' || coalesce(v_row.venue, '') || ' ' || coalesce(v_row.vendor_name, '')),
    'events',
    v_price_min,
    v_price_max,
    v_row.lat,
    v_row.lng,
    null,
    jsonb_build_object(
      'in_stock', true,
      'verified', true,
      'below_median', false
    ),
    true
  )
  on conflict (entity_kind, entity_id) do update
  set
    title = excluded.title,
    body = excluded.body,
    category_path = excluded.category_path,
    price_min_ngwee = excluded.price_min_ngwee,
    price_max_ngwee = excluded.price_max_ngwee,
    lat = excluded.lat,
    lng = excluded.lng,
    locale_terms = excluded.locale_terms,
    boost_signals = excluded.boost_signals,
    is_public = true,
    updated_at = timezone('utc', now());
end;
$$;

-- vendor: title=display_name, body=description, geo from first location; status='active' only.
create or replace function public.search_upsert_vendor(p_vendor_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
begin
  select
    v.id,
    v.slug,
    v.display_name,
    v.description,
    v.status,
    v.kyc_tier,
    v.preferred_badge,
    loc.lat,
    loc.lng
  into v_row
  from public.vendors v
  left join lateral (
    select vl.lat, vl.lng
    from public.vendor_locations vl
    where vl.vendor_id = v.id
    order by vl.created_at
    limit 1
  ) loc on true
  where v.id = p_vendor_id;

  if not found then
    perform public.search_remove_document('vendor', p_vendor_id);
    return;
  end if;

  if v_row.status <> 'active' then
    perform public.search_mark_unpublished('vendor', p_vendor_id);
    return;
  end if;

  insert into public.search_documents (
    entity_kind,
    entity_id,
    title,
    body,
    category_path,
    price_min_ngwee,
    price_max_ngwee,
    lat,
    lng,
    locale_terms,
    boost_signals,
    is_public
  )
  values (
    'vendor',
    v_row.id,
    v_row.display_name,
    coalesce(v_row.description, ''),
    null,
    null,
    null,
    v_row.lat,
    v_row.lng,
    array[v_row.slug],
    jsonb_build_object(
      'in_stock', true,
      'verified', coalesce(v_row.kyc_tier, 0) >= 2 or coalesce(v_row.preferred_badge, false),
      'below_median', false
    ),
    true
  )
  on conflict (entity_kind, entity_id) do update
  set
    title = excluded.title,
    body = excluded.body,
    category_path = excluded.category_path,
    price_min_ngwee = excluded.price_min_ngwee,
    price_max_ngwee = excluded.price_max_ngwee,
    lat = excluded.lat,
    lng = excluded.lng,
    locale_terms = excluded.locale_terms,
    boost_signals = excluded.boost_signals,
    is_public = true,
    updated_at = timezone('utc', now());
end;
$$;

-- Re-sync child entities when a vendor publish state changes.
create or replace function public.search_cascade_vendor_children(p_vendor_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_listing_id uuid;
  v_service_id uuid;
  v_event_id uuid;
begin
  for v_listing_id in
    select vl.id from public.vendor_listings vl where vl.vendor_id = p_vendor_id
  loop
    perform public.search_upsert_listing(v_listing_id);
  end loop;

  for v_service_id in
    select s.id from public.services s where s.vendor_id = p_vendor_id
  loop
    perform public.search_upsert_service(v_service_id);
  end loop;

  for v_event_id in
    select e.id from public.events e where e.organiser_vendor_id = p_vendor_id
  loop
    perform public.search_upsert_event(v_event_id);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- Source-table sync triggers
-- ---------------------------------------------------------------------------

create or replace function public.search_sync_products_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    perform public.search_remove_document('product', old.id);
    return old;
  end if;

  perform public.search_upsert_product(new.id);
  return new;
end;
$$;

create trigger products_search_sync
  after insert or update or delete on public.products
  for each row
  execute function public.search_sync_products_trigger();

create or replace function public.search_sync_listings_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    perform public.search_remove_document('listing', old.id);
    return old;
  end if;

  perform public.search_upsert_listing(new.id);
  return new;
end;
$$;

create trigger vendor_listings_search_sync
  after insert or update or delete on public.vendor_listings
  for each row
  execute function public.search_sync_listings_trigger();

create or replace function public.search_sync_services_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    perform public.search_remove_document('service', old.id);
    return old;
  end if;

  perform public.search_upsert_service(new.id);
  return new;
end;
$$;

create trigger services_search_sync
  after insert or update or delete on public.services
  for each row
  execute function public.search_sync_services_trigger();

create or replace function public.search_sync_events_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    perform public.search_remove_document('event', old.id);
    return old;
  end if;

  perform public.search_upsert_event(new.id);

  return new;
end;
$$;

create trigger events_search_sync
  after insert or update or delete on public.events
  for each row
  execute function public.search_sync_events_trigger();

create or replace function public.search_sync_vendors_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    perform public.search_remove_document('vendor', old.id);
    return old;
  end if;

  perform public.search_upsert_vendor(new.id);

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    perform public.search_cascade_vendor_children(new.id);
  end if;

  return new;
end;
$$;

create trigger vendors_search_sync
  after insert or update or delete on public.vendors
  for each row
  execute function public.search_sync_vendors_trigger();

-- Ticket type price changes affect event price range in the projection.
create or replace function public.search_sync_ticket_types_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_event_id uuid;
begin
  v_event_id := coalesce(new.event_id, old.event_id);
  if v_event_id is not null then
    perform public.search_upsert_event(v_event_id);
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create trigger ticket_types_search_sync
  after insert or update or delete on public.ticket_types
  for each row
  execute function public.search_sync_ticket_types_trigger();

-- ---------------------------------------------------------------------------
-- Query expansion + RRF search (FTS + trgm + vector lanes)
-- ---------------------------------------------------------------------------

create or replace function public.expand_search_terms(p_query text)
returns text
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
  v_base text := nullif(trim(p_query), '');
  v_extra text;
begin
  if v_base is null then
    return null;
  end if;

  select string_agg(distinct s.canonical, ' ')
  into v_extra
  from public.synonyms s
  where s.term = lower(v_base)
     or lower(v_base) like '%' || s.term || '%';

  return trim(both ' ' from v_base || coalesce(' ' || v_extra, ''));
end;
$$;

comment on function public.expand_search_terms(text) is
  'Appends canonical synonym terms for fuzzy/FTS query expansion (e.g. chitange → chitenge).';

create or replace function public.search_apply_boost(
  p_base_score double precision,
  p_boost_signals jsonb
)
returns double precision
language sql
immutable
as $$
  select p_base_score
    * (
      1.0
      + case when coalesce((p_boost_signals ->> 'in_stock')::boolean, false) then 0.10 else 0.0 end
      + case when coalesce((p_boost_signals ->> 'verified')::boolean, false) then 0.05 else 0.0 end
      + case when coalesce((p_boost_signals ->> 'below_median')::boolean, false) then 0.05 else 0.0 end
    );
$$;

create or replace function public.search_rrf(
  query text,
  query_embedding vector(384) default null,
  filters jsonb default '{}'::jsonb
)
returns table (
  id uuid,
  entity_kind text,
  entity_id uuid,
  title text,
  body text,
  category_path text,
  price_min_ngwee bigint,
  price_max_ngwee bigint,
  lat double precision,
  lng double precision,
  locale_terms text[],
  boost_signals jsonb,
  rrf_score double precision
)
language sql
stable
security definer
set search_path = public, extensions
as $$
  with params as (
    select
      nullif(trim(query), '') as raw_query,
      coalesce(public.expand_search_terms(query), nullif(trim(query), '')) as expanded_query,
      coalesce(filters, '{}'::jsonb) as f,
      60.0::double precision as rrf_k
  ),
  filtered as (
    select sd.*
    from public.search_documents sd
    cross join params p
    where sd.is_public = true
      and (
        p.f ->> 'entity_kind' is null
        or sd.entity_kind = p.f ->> 'entity_kind'
      )
      and (
        p.f ->> 'category_path' is null
        or sd.category_path like (p.f ->> 'category_path') || '%'
      )
      and (
        p.f ->> 'price_min_ngwee' is null
        or sd.price_max_ngwee is null
        or sd.price_max_ngwee >= (p.f ->> 'price_min_ngwee')::bigint
      )
      and (
        p.f ->> 'price_max_ngwee' is null
        or sd.price_min_ngwee is null
        or sd.price_min_ngwee <= (p.f ->> 'price_max_ngwee')::bigint
      )
  ),
  fts_lane as (
    select
      f.id,
      row_number() over (
        order by ts_rank_cd(f.tsv, websearch_to_tsquery('simple', p.expanded_query)) desc
      ) as lane_rank
    from filtered f
    cross join params p
    where p.expanded_query is not null
      and f.tsv @@ websearch_to_tsquery('simple', p.expanded_query)
    limit 100
  ),
  trgm_lane as (
    select
      f.id,
      row_number() over (
        order by greatest(
          similarity(f.title, p.raw_query),
          similarity(coalesce(array_to_string(f.locale_terms, ' '), ''), p.raw_query)
        ) desc
      ) as lane_rank
    from filtered f
    cross join params p
    where p.raw_query is not null
      and (
        f.title % p.raw_query
        or coalesce(array_to_string(f.locale_terms, ' '), '') % p.raw_query
        or exists (
          select 1
          from public.synonyms s
          where s.term = lower(p.raw_query)
            and (
              f.title ilike '%' || s.canonical || '%'
              or coalesce(array_to_string(f.locale_terms, ' '), '') ilike '%' || s.canonical || '%'
            )
        )
      )
    limit 100
  ),
  vector_lane as (
    select
      f.id,
      row_number() over (order by f.embedding <=> p.query_embedding) as lane_rank
    from filtered f
    cross join params p
    where p.query_embedding is not null
      and f.embedding is not null
    limit 100
  ),
  fused as (
    select
      lanes.id,
      sum(1.0 / (p.rrf_k + lanes.lane_rank)) as base_score
    from (
      select id, lane_rank from fts_lane
      union all
      select id, lane_rank from trgm_lane
      union all
      select id, lane_rank from vector_lane
    ) lanes
    cross join params p
    group by lanes.id
  )
  select
    sd.id,
    sd.entity_kind,
    sd.entity_id,
    sd.title,
    sd.body,
    sd.category_path,
    sd.price_min_ngwee,
    sd.price_max_ngwee,
    sd.lat,
    sd.lng,
    sd.locale_terms,
    sd.boost_signals,
    public.search_apply_boost(f.base_score, sd.boost_signals) as rrf_score
  from fused f
  join filtered sd on sd.id = f.id
  order by public.search_apply_boost(f.base_score, sd.boost_signals) desc, sd.title asc;
$$;

comment on function public.search_rrf(text, vector, jsonb) is
  'Reciprocal Rank Fusion across FTS (GIN tsv), trgm fuzzy (GIN title), and optional vector (HNSW embedding) lanes.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.search_documents enable row level security;
alter table public.synonyms enable row level security;

alter table public.search_documents force row level security;
alter table public.synonyms force row level security;

-- search_documents: public read of published projection only; no client writes.
create policy search_documents_public_select
  on public.search_documents
  for select
  using (is_public = true);

comment on policy search_documents_public_select on public.search_documents is
  'Anonymous and authenticated clients may read only public search projections; unpublished entities never surface.';

create policy search_documents_service_role_all
  on public.search_documents
  for all
  to service_role
  using (true)
  with check (true);

comment on policy search_documents_service_role_all on public.search_documents is
  'Sync triggers and service_role may write search projections; clients cannot inject documents.';

-- synonyms: public read; admin write.
create policy synonyms_public_select
  on public.synonyms
  for select
  using (true);

comment on policy synonyms_public_select on public.synonyms is
  'Synonym table is publicly readable for search expansion transparency.';

create policy synonyms_admin_insert
  on public.synonyms
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy synonyms_admin_update
  on public.synonyms
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy synonyms_admin_delete
  on public.synonyms
  for delete
  to authenticated
  using (public.has_role('admin'));

comment on policy synonyms_admin_insert on public.synonyms is
  'Only platform admins may add locale synonym rows.';
comment on policy synonyms_admin_update on public.synonyms is
  'Only platform admins may update synonym mappings.';
comment on policy synonyms_admin_delete on public.synonyms is
  'Only platform admins may delete synonym rows.';

-- ---------------------------------------------------------------------------
-- Data API grants
-- ---------------------------------------------------------------------------

grant select on table public.search_documents to anon, authenticated;
grant select, insert, update, delete on table public.search_documents to service_role;

grant select on table public.synonyms to anon, authenticated;
grant select, insert, update, delete on table public.synonyms to authenticated, service_role;

grant execute on function public.search_rrf(text, vector, jsonb) to anon, authenticated, service_role;
grant execute on function public.expand_search_terms(text) to anon, authenticated, service_role;
