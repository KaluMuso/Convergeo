-- M07-P01 carts — migration apply, RLS owner matrix, owner check constraint
-- Requires migrations 0001–0012 applied.
-- Run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0012_carts.test.sql

\set ON_ERROR_STOP on

begin;

set local search_path to public, extensions, auth;

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

select extensions.plan(8);

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
  )
  on conflict (id) do nothing;
end;
$$;

select pg_temp.seed_auth_user(
  '11111111-1111-1111-1111-111111111111',
  'customer-a@test.local'
);
select pg_temp.seed_auth_user(
  '22222222-2222-2222-2222-222222222222',
  'customer-b@test.local'
);
select pg_temp.seed_auth_user(
  '55555555-5555-5555-5555-555555555555',
  'stranger@test.local'
);

insert into public.profiles (id, phone, display_name)
values
  ('11111111-1111-1111-1111-111111111111', '+260971000001', 'Customer A'),
  ('22222222-2222-2222-2222-222222222222', '+260971000002', 'Customer B'),
  ('55555555-5555-5555-5555-555555555555', '+260971000005', 'Stranger')
on conflict (id) do nothing;

insert into public.user_roles (user_id, role)
values
  ('11111111-1111-1111-1111-111111111111', 'customer'),
  ('22222222-2222-2222-2222-222222222222', 'customer'),
  ('55555555-5555-5555-5555-555555555555', 'customer')
on conflict do nothing;

insert into public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
  'shop-a',
  'Shop A',
  'active',
  2
)
on conflict (id) do nothing;

insert into public.categories (id, name, slug, path, commission_key)
values (
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'Electronics',
  'electronics',
  'electronics',
  'electronics'
)
on conflict (id) do nothing;

insert into public.products (id, name, slug, category_id, status)
values (
  'dddddddd-dddd-dddd-dddd-dddddddddddd',
  'Test Phone',
  'test-phone',
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'active'
)
on conflict (id) do nothing;

insert into public.vendor_listings (
  id,
  vendor_id,
  product_id,
  title_override,
  price_ngwee,
  condition,
  stock_mode,
  stock_qty,
  wholesale,
  moq,
  status
)
values (
  '10101010-1010-1010-1010-101010101010',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'dddddddd-dddd-dddd-dddd-dddddddddddd',
  'Test Listing',
  100000,
  'new',
  'tracked',
  50,
  false,
  1,
  'active'
)
on conflict (id) do nothing;

insert into public.carts (id, user_id, status)
values (
  'f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0',
  '11111111-1111-1111-1111-111111111111',
  'active'
)
on conflict (id) do nothing;

insert into public.carts (id, user_id, status)
values (
  'f1f1f1f1-f1f1-f1f1-f1f1-f1f1f1f1f1f1',
  '22222222-2222-2222-2222-222222222222',
  'active'
)
on conflict (id) do nothing;

insert into public.cart_items (id, cart_id, listing_id, qty, unit_price_ngwee, wholesale)
values (
  'e0e0e0e0-e0e0-e0e0-e0e0-e0e0e0e0e0e0',
  'f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0',
  '10101010-1010-1010-1010-101010101010',
  2,
  100000,
  false
)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Check constraint: carts require user_id or guest_token
-- ---------------------------------------------------------------------------

select extensions.throws_ok(
  $$insert into public.carts (id, status) values (
      'badbadbad-badbadbad-badbadbad-badbadbadbad', 'active'
    )$$,
  '23514',
  null,
  'carts owner check rejects row with neither user_id nor guest_token'
);

-- ---------------------------------------------------------------------------
-- RLS matrix
-- ---------------------------------------------------------------------------

create or replace function pg_temp.set_auth(target_id uuid)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
  format('{"sub":"%s","role":"authenticated"}', target_id),
    true
  );
  perform set_config('role', 'authenticated', true);
end;
$$;

set session authorization vergeo_rls_tester;

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.carts
    where user_id = '11111111-1111-1111-1111-111111111111'
  ),
  1,
  'customer A reads own cart'
);

select extensions.is(
  (
    select count(*)::int
    from public.carts
    where user_id = '22222222-2222-2222-2222-222222222222'
  ),
  0,
  'customer A cannot read customer B cart'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.cart_items ci
    join public.carts c on c.id = ci.cart_id
    where c.user_id = '11111111-1111-1111-1111-111111111111'
  ),
  1,
  'customer A reads own cart items'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.is(
  (select count(*)::int from public.carts),
  0,
  'stranger reads no carts'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.is(
  (select count(*)::int from public.cart_items),
  0,
  'stranger reads no cart items'
);

reset session authorization;

select extensions.finish();

rollback;
