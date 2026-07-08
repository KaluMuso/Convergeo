-- M03-P08 search projection — sync triggers, RRF fusion, EXPLAIN index checks
-- Requires: 0001–0005, 0008, 0009_search.sql
-- Run: supabase test db (pgTAP) after db reset

begin;

set local search_path to public, extensions, auth;

select extensions.plan(22);

-- ---------------------------------------------------------------------------
-- Fixture seed (service_role bypasses RLS)
-- ---------------------------------------------------------------------------

set local role service_role;

create or replace function pg_temp.seed_auth_user(target_id uuid, email text)
returns void
language plpgsql
as $$
begin
  insert into auth.users (
    instance_id,
    id,
    aud,
    role,
    email,
    encrypted_password,
    email_confirmed_at,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at
  )
  values (
    '00000000-0000-0000-0000-000000000000',
    target_id,
    'authenticated',
    'authenticated',
    email,
    'test-password-hash',
    timezone('utc', now()),
    '{}'::jsonb,
    '{}'::jsonb,
    timezone('utc', now()),
    timezone('utc', now())
  );
end;
$$;

select pg_temp.seed_auth_user(
  '11111111-1111-1111-1111-111111111111',
  'search-vendor@test.local'
);

insert into public.profiles (id, phone, display_name)
values ('11111111-1111-1111-1111-111111111111', '+260971000099', 'Search Vendor');

insert into public.vendors (
  id,
  owner_user_id,
  slug,
  display_name,
  description,
  status,
  kyc_tier
)
values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
  'search-shop',
  'Search Shop',
  'Trusted Lusaka vendor',
  'active',
  2
);

insert into public.vendor_locations (vendor_id, lat, lng, landmark)
values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  -15.3875,
  28.3228,
  'Near Manda Hill'
);

insert into public.categories (
  id,
  name,
  slug,
  path,
  commission_key,
  position
)
values (
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'Fashion',
  'fashion',
  'fashion',
  'fashion',
  0
);

-- ---------------------------------------------------------------------------
-- Product sync: active projects, pending does not
-- ---------------------------------------------------------------------------

insert into public.products (
  id,
  name,
  slug,
  category_id,
  status,
  aliases,
  brand
)
values (
  'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
  'Chitenge Wrap',
  'chitenge-wrap',
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'active',
  array['chitenge', 'chitange'],
  'ZedFabrics'
);

select extensions.is(
  (
    select count(*)::int
    from public.search_documents
    where entity_kind = 'product'
      and entity_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
      and is_public = true
  ),
  1,
  'active product creates public search_documents row'
);

insert into public.products (
  id,
  name,
  slug,
  category_id,
  status
)
values (
  'ffffffff-ffff-ffff-ffff-ffffffffffff',
  'Draft Scarf',
  'draft-scarf',
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'pending_moderation'
);

select extensions.is(
  (
    select count(*)::int
    from public.search_documents
    where entity_kind = 'product'
      and entity_id = 'ffffffff-ffff-ffff-ffff-ffffffffffff'
  ),
  0,
  'pending_moderation product is never projected'
);

update public.products
set status = 'merged'
where id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

select extensions.is(
  (
    select is_public
    from public.search_documents
    where entity_kind = 'product'
      and entity_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  ),
  false,
  'unpublished product sets is_public=false'
);

update public.products
set status = 'active'
where id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

-- ---------------------------------------------------------------------------
-- Listing sync
-- ---------------------------------------------------------------------------

insert into public.vendor_listings (
  id,
  vendor_id,
  product_id,
  price_ngwee,
  condition,
  stock_mode,
  stock_qty,
  status
)
values (
  '10101010-1010-1010-1010-101010101010',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
  85000,
  'new',
  'tracked',
  4,
  'active'
);

select extensions.is(
  (
    select price_min_ngwee
    from public.search_documents
    where entity_kind = 'listing'
      and entity_id = '10101010-1010-1010-1010-101010101010'
  ),
  85000::bigint,
  'active listing syncs price and projects publicly'
);

insert into public.vendor_listings (
  id,
  vendor_id,
  product_id,
  price_ngwee,
  condition,
  stock_mode,
  status
)
values (
  '20202020-2020-2020-2020-202020202020',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
  50000,
  'new',
  'always_available',
  'draft'
);

select extensions.is(
  (
    select count(*)::int
    from public.search_documents
    where entity_kind = 'listing'
      and entity_id = '20202020-2020-2020-2020-202020202020'
  ),
  0,
  'draft listing is never projected'
);

update public.vendor_listings
set status = 'paused'
where id = '10101010-1010-1010-1010-101010101010';

select extensions.is(
  (
    select is_public
    from public.search_documents
    where entity_kind = 'listing'
      and entity_id = '10101010-1010-1010-1010-101010101010'
  ),
  false,
  'unpublished listing sets is_public=false'
);

delete from public.vendor_listings
where id = '20202020-2020-2020-2020-202020202020';

-- ---------------------------------------------------------------------------
-- Service sync
-- ---------------------------------------------------------------------------

insert into public.services (
  id,
  vendor_id,
  category,
  title,
  description,
  from_price_ngwee,
  status
)
values (
  '30303030-3030-3030-3030-303030303030',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'services/plumbing',
  'Pipe Repair',
  'Fast plumbing in Lusaka',
  150000,
  'active'
);

select extensions.ok(
  exists (
    select 1
    from public.search_documents
    where entity_kind = 'service'
      and entity_id = '30303030-3030-3030-3030-303030303030'
      and is_public = true
  ),
  'active service is projected'
);

update public.services
set status = 'paused'
where id = '30303030-3030-3030-3030-303030303030';

select extensions.is(
  (
    select is_public
    from public.search_documents
    where entity_kind = 'service'
      and entity_id = '30303030-3030-3030-3030-303030303030'
  ),
  false,
  'paused service sets is_public=false'
);

-- ---------------------------------------------------------------------------
-- Event sync
-- ---------------------------------------------------------------------------

insert into public.events (
  id,
  organiser_vendor_id,
  title,
  slug,
  description,
  venue,
  lat,
  lng,
  status
)
values (
  '40404040-4040-4040-4040-404040404040',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Zambia Music Night',
  'zambia-music-night',
  'Live music in Lusaka',
  'Showgrounds',
  -15.4167,
  28.2833,
  'published'
);

insert into public.event_instances (event_id, starts_at, capacity)
values (
  '40404040-4040-4040-4040-404040404040',
  timezone('utc', now()) + interval '14 days',
  500
);

insert into public.ticket_types (event_id, kind, name, price_ngwee)
values
  ('40404040-4040-4040-4040-404040404040', 'fixed', 'General', 50000),
  ('40404040-4040-4040-4040-404040404040', 'fixed', 'VIP', 150000);

select extensions.is(
  (
    select price_min_ngwee
    from public.search_documents
    where entity_kind = 'event'
      and entity_id = '40404040-4040-4040-4040-404040404040'
  ),
  50000::bigint,
  'published event syncs ticket price range'
);

insert into public.events (
  id,
  organiser_vendor_id,
  title,
  slug,
  status
)
values (
  '50505050-5050-5050-5050-505050505050',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Draft Gig',
  'draft-gig',
  'draft'
);

select extensions.is(
  (
    select count(*)::int
    from public.search_documents
    where entity_kind = 'event'
      and entity_id = '50505050-5050-5050-5050-505050505050'
  ),
  0,
  'draft event is never projected'
);

update public.events
set status = 'cancelled'
where id = '40404040-4040-4040-4040-404040404040';

select extensions.is(
  (
    select is_public
    from public.search_documents
    where entity_kind = 'event'
      and entity_id = '40404040-4040-4040-4040-404040404040'
  ),
  false,
  'cancelled event sets is_public=false'
);

-- ---------------------------------------------------------------------------
-- Vendor sync + cascade on suspend
-- ---------------------------------------------------------------------------

select extensions.ok(
  exists (
    select 1
    from public.search_documents
    where entity_kind = 'vendor'
      and entity_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
      and is_public = true
  ),
  'active vendor is projected'
);

update public.vendor_listings
set status = 'active'
where id = '10101010-1010-1010-1010-101010101010';

update public.services
set status = 'active'
where id = '30303030-3030-3030-3030-303030303030';

update public.events
set status = 'published'
where id = '40404040-4040-4040-4040-404040404040';

update public.vendors
set status = 'suspended'
where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

select extensions.is(
  (
    select is_public
    from public.search_documents
    where entity_kind = 'vendor'
      and entity_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  ),
  false,
  'suspended vendor sets is_public=false'
);

select extensions.is(
  (
    select count(*)::int
    from public.search_documents
    where entity_id in (
      '10101010-1010-1010-1010-101010101010',
      '30303030-3030-3030-3030-303030303030',
      '40404040-4040-4040-4040-404040404040'
    )
      and is_public = true
  ),
  0,
  'vendor suspend cascades is_public=false to child listings/services/events'
);

update public.vendors
set status = 'active'
where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

-- ---------------------------------------------------------------------------
-- Synonym seeds
-- ---------------------------------------------------------------------------

select extensions.ok(
  exists (
    select 1
    from public.synonyms
    where term = 'chitange'
      and canonical = 'chitenge'
  ),
  'synonyms seeded: chitange → chitenge'
);

-- ---------------------------------------------------------------------------
-- search_rrf fusion (exact + fuzzy synonym + vector)
-- ---------------------------------------------------------------------------

update public.products
set status = 'active'
where id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

update public.vendor_listings
set status = 'active'
where id = '10101010-1010-1010-1010-101010101010';

update public.search_documents
set embedding = (
  ('[' || (select string_agg('0.1', ',') from generate_series(1, 384)) || ']')::vector(384)
)
where entity_kind = 'product'
  and entity_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

select extensions.ok(
  (
    select entity_kind
    from public.search_rrf('Chitenge', null, '{}'::jsonb)
    limit 1
  ) in ('product', 'listing'),
  'search_rrf returns chitenge product/listing for exact query'
);

select extensions.ok(
  (
    select count(*) >= 1
    from public.search_rrf('chitange', null, '{}'::jsonb)
    where title ilike '%chitenge%'
       or coalesce(array_to_string(locale_terms, ' '), '') ilike '%chitenge%'
  ),
  'search_rrf fuzzy lane matches chitange → chitenge synonym'
);

select extensions.ok(
  exists (
    select 1
    from public.search_rrf(
      'fabric',
      ('[' || (select string_agg('0.1', ',') from generate_series(1, 384)) || ']')::vector(384),
      '{"entity_kind":"product"}'::jsonb
    )
    where entity_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  ),
  'search_rrf vector lane returns product with matching dummy embedding'
);

-- ---------------------------------------------------------------------------
-- RLS: private projections hidden from anon
-- ---------------------------------------------------------------------------

update public.products
set status = 'pending_moderation'
where id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';

set local role anon;

select extensions.is(
  (
    select count(*)::int
    from public.search_documents
    where entity_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  ),
  0,
  'anon cannot read unpublished search_documents via RLS'
);

reset role;
set local role service_role;

-- ---------------------------------------------------------------------------
-- EXPLAIN index checks (three lanes)
-- ---------------------------------------------------------------------------

create temp table explain_plans (lane text, plan text);

do $$
declare
  plan_text text := '';
  r record;
begin
  for r in
    explain (costs off)
    select sd.id
    from public.search_documents sd
    where sd.is_public = true
      and sd.tsv @@ websearch_to_tsquery('simple', 'chitenge')
    limit 10
  loop
    plan_text := plan_text || r."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (lane, plan) values ('fts', plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where lane = 'fts'
      and (
        plan ilike '%search_documents_tsv_gin_idx%'
        or plan ilike '%Bitmap Index Scan%tsv%'
      )
  ),
  'FTS lane uses GIN(tsv) index'
);

truncate explain_plans;

do $$
declare
  plan_text text := '';
  r record;
begin
  for r in
    explain (costs off)
    select sd.id
    from public.search_documents sd
    where sd.is_public = true
      and sd.title % 'chitange'
    limit 10
  loop
    plan_text := plan_text || r."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (lane, plan) values ('trgm', plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where lane = 'trgm'
      and (
        plan ilike '%search_documents_title_trgm_idx%'
        or plan ilike '%Bitmap Index Scan%title%'
      )
  ),
  'trgm fuzzy lane uses GIN(title gin_trgm_ops) index'
);

truncate explain_plans;

do $$
declare
  plan_text text := '';
  r record;
  v_query vector(384) := ('[' || (select string_agg('0.1', ',') from generate_series(1, 384)) || ']')::vector(384);
begin
  for r in
    explain (costs off)
    select sd.id
    from public.search_documents sd
    where sd.is_public = true
      and sd.embedding is not null
    order by sd.embedding <=> v_query
    limit 5
  loop
    plan_text := plan_text || r."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (lane, plan) values ('vector', plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where lane = 'vector'
      and (
        plan ilike '%search_documents_embedding_hnsw_idx%'
        or plan ilike '%Index Scan%embedding%'
      )
  ),
  'vector lane uses HNSW(embedding) index'
);

select * from extensions.finish();
rollback;
