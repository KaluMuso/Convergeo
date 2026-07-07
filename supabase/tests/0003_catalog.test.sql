-- M03-P02 catalog schema — constraint + RLS matrix + EXPLAIN index checks
-- Requires: 0001_extensions.sql, 0002_identity_vendors.sql, 0003_catalog.sql, 0008_config.sql
-- Run: supabase test db (pgTAP) after db reset

begin;

set local search_path to public, extensions, auth;

-- Non-superuser for RLS/trigger tests (postgres session_user bypasses guard triggers).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'vergeo_rls_tester') then
    create role vergeo_rls_tester login password 'test' nosuperuser nobypassrls;
    grant authenticated to vergeo_rls_tester;
    grant anon to vergeo_rls_tester;
  end if;
end;
$$;

grant all on table auth.users to service_role;
grant usage on schema public, auth, extensions to vergeo_rls_tester;
grant all on all tables in schema public to vergeo_rls_tester;
grant execute on all functions in schema public to vergeo_rls_tester;

select extensions.plan(18);

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
  'vendor-a@test.local'
);
select pg_temp.seed_auth_user(
  '22222222-2222-2222-2222-222222222222',
  'vendor-b@test.local'
);
select pg_temp.seed_auth_user(
  '33333333-3333-3333-3333-333333333333',
  'admin@test.local'
);

insert into public.profiles (id, phone, display_name)
values
  ('11111111-1111-1111-1111-111111111111', '+260971000001', 'Vendor A'),
  ('22222222-2222-2222-2222-222222222222', '+260971000002', 'Vendor B'),
  ('33333333-3333-3333-3333-333333333333', '+260971000003', 'Admin User');

insert into public.user_roles (user_id, role)
values
  ('11111111-1111-1111-1111-111111111111', 'customer'),
  ('11111111-1111-1111-1111-111111111111', 'vendor'),
  ('22222222-2222-2222-2222-222222222222', 'customer'),
  ('22222222-2222-2222-2222-222222222222', 'vendor'),
  ('33333333-3333-3333-3333-333333333333', 'admin');

insert into public.vendors (
  id,
  owner_user_id,
  slug,
  display_name,
  status,
  kyc_tier
)
values
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'shop-a',
    'Shop A',
    'active',
    2
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '22222222-2222-2222-2222-222222222222',
    'shop-b',
    'Shop B',
    'active',
    2
  );

insert into public.categories (
  id,
  name,
  slug,
  path,
  commission_key,
  position
)
values
  (
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    'Electronics',
    'electronics',
    'electronics',
    'electronics',
    0
  ),
  (
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'Phones',
    'phones',
    'electronics/phones',
    'electronics',
    1
  );

insert into public.products (
  id,
  name,
  slug,
  category_id,
  status,
  aliases
)
values
  (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
    'Active Phone',
    'active-phone',
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'active',
    array['foni']
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
    'Pending Phone',
    'pending-phone',
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'pending_moderation',
    '{}'
  );

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
values
  (
    '10101010-1010-1010-1010-101010101010',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
    250000,
    'new',
    'tracked',
    5,
    'active'
  ),
  (
    '20202020-2020-2020-2020-202020202020',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    null,
    150000,
    'new',
    'always_available',
    null,
    'draft'
  ),
  (
    '30303030-3030-3030-3030-303030303030',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
    240000,
    'new',
    'tracked',
    3,
    'active'
  );

insert into public.listing_images (listing_id, cloudinary_public_id, position)
select
  '10101010-1010-1010-1010-101010101010',
  'vergeo5/listings/img-' || gs::text,
  gs
from generate_series(1, 8) as gs;

create or replace function pg_temp.set_auth(target_id uuid)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    json_build_object(
      'sub', target_id::text,
      'role', 'authenticated',
      'aal', 'aal1'
    )::text,
    true
  );
  execute 'set local role authenticated';
end;
$$;

create or replace function pg_temp.set_anon()
returns void
language plpgsql
as $$
begin
  perform set_config('request.jwt.claims', '', true);
  execute 'set local role anon';
end;
$$;

reset role;

-- ---------------------------------------------------------------------------
-- Constraint tests (service_role / superuser)
-- ---------------------------------------------------------------------------

set local role service_role;

select extensions.throws_ok(
  $$insert into public.vendor_listings (
    vendor_id, price_ngwee, condition, stock_mode, status
  ) values (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', -100, 'new', 'tracked', 'draft'
  )$$,
  '23514',
  null,
  'negative price_ngwee rejected'
);

select extensions.throws_ok(
  $$insert into public.vendor_listings (
    vendor_id, price_ngwee, condition, stock_mode, moq, status
  ) values (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 10000, 'new', 'tracked', 0, 'draft'
  )$$,
  '23514',
  null,
  'moq < 1 rejected'
);

select extensions.throws_ok(
  $$insert into public.vendor_listings (
    vendor_id, price_ngwee, condition, stock_mode, price_tiers, status
  ) values (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    10000,
    'new',
    'tracked',
    '[{"min_qty": 5, "price_ngwee": "not-a-number"}]'::jsonb,
    'draft'
  )$$,
  '23514',
  null,
  'malformed price_tiers rejected'
);

select extensions.throws_ok(
  $$insert into public.listing_images (
    listing_id, cloudinary_public_id, position
  ) values (
    '20202020-2020-2020-2020-202020202020', 'vergeo5/listings/img-9', 9
  )$$,
  '23514',
  null,
  'position > 8 rejected'
);

insert into public.listing_images (listing_id, cloudinary_public_id, position)
values ('20202020-2020-2020-2020-202020202020', 'vergeo5/listings/draft-1', 1);

select extensions.throws_ok(
  $$insert into public.listing_images (
    listing_id, cloudinary_public_id, position
  ) values (
    '20202020-2020-2020-2020-202020202020', 'vergeo5/listings/draft-dup', 1
  )$$,
  '23505',
  null,
  'duplicate listing_id+position rejected'
);

select extensions.throws_ok(
  $$insert into public.listing_images (
    listing_id, cloudinary_public_id, position
  ) values (
    '10101010-1010-1010-1010-101010101010', 'vergeo5/listings/img-overflow', 2
  )$$,
  'P0001',
  null,
  '9th image rejected by count trigger'
);

-- ---------------------------------------------------------------------------
-- RLS matrix (non-superuser session)
-- ---------------------------------------------------------------------------

set session authorization vergeo_rls_tester;

select pg_temp.set_anon();
select extensions.is(
  (select count(*)::int from public.products where status = 'active'),
  1,
  'anon reads only active products'
);
select extensions.is(
  (select count(*)::int from public.products),
  1,
  'anon cannot read pending_moderation products'
);
select extensions.is(
  (
    select count(*)::int
    from public.vendor_listings
    where status = 'active'
  ),
  2,
  'anon reads active listings on active vendors'
);
select extensions.is(
  (
    select count(*)::int
    from public.vendor_listings
    where id = '20202020-2020-2020-2020-202020202020'
  ),
  0,
  'anon cannot read draft listings'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
update public.vendor_listings
set price_ngwee = 1
where id = '30303030-3030-3030-3030-303030303030';
select extensions.is(
  (
    select price_ngwee
    from public.vendor_listings
    where id = '30303030-3030-3030-3030-303030303030'
  ),
  240000::bigint,
  'vendor A cannot update vendor B listing'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.lives_ok(
  $$insert into public.products (
    name, slug, category_id, status
  ) values (
    'User Proposed', 'user-proposed', 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'pending_moderation'
  )$$,
  'authenticated insert as pending_moderation allowed'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.products (
    name, slug, category_id, status
  ) values (
    'Self Approved', 'self-approved', 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'active'
  )$$,
  '42501',
  null,
  'authenticated insert as active rejected by RLS'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$update public.vendor_listings
    set status = 'removed'
    where id = '20202020-2020-2020-2020-202020202020'$$,
  'P0001',
  null,
  'owner cannot set listing status to removed'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.lives_ok(
  $$update public.vendor_listings
    set status = 'active'
    where id = '20202020-2020-2020-2020-202020202020'$$,
  'owner may draft to active'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.lives_ok(
  $$update public.vendor_listings
    set status = 'removed'
    where id = '30303030-3030-3030-3030-303030303030'$$,
  'admin may set listing status to removed'
);

reset session authorization;

-- ---------------------------------------------------------------------------
-- EXPLAIN index checks (hot lookups)
-- ---------------------------------------------------------------------------

set local role service_role;

create temp table explain_plans (plan text);

do $$
declare
  plan_text text := '';
  r record;
begin
  for r in
    explain (costs off)
    select id
    from public.vendor_listings
    where product_id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
      and status = 'active'
  loop
    plan_text := plan_text || r."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (plan) values (plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where plan ilike '%vendor_listings_product_id_active_idx%'
       or plan ilike '%Index Scan%vendor_listings%product_id%'
  ),
  'active listings by product_id use product_id index'
);

truncate explain_plans;

do $$
declare
  plan_text text := '';
  r record;
begin
  for r in
    explain (costs off)
    select id
    from public.categories
    where path like 'electronics/%'
  loop
    plan_text := plan_text || r."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (plan) values (plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where plan ilike '%categories_path_idx%'
       or plan ilike '%Index Scan%categories%path%'
  ),
  'category path prefix lookup uses path index'
);

select * from extensions.finish();
rollback;
