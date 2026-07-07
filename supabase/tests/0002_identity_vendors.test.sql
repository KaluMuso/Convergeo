-- M03-P01 policy smoke tests (pgTAP via `supabase test db`).

begin;

set local search_path to public, extensions, auth;

select extensions.plan(25);

-- Seed fixtures with service_role (bypasses RLS); assertions run as client roles.
set local role service_role;

-- ---------------------------------------------------------------------------
-- Fixture UUIDs (stable literals for the matrix)
-- ---------------------------------------------------------------------------

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
  'owner@test.local'
);
select pg_temp.seed_auth_user(
  '22222222-2222-2222-2222-222222222222',
  'other@test.local'
);
select pg_temp.seed_auth_user(
  '33333333-3333-3333-3333-333333333333',
  'admin@test.local'
);

insert into public.profiles (id, phone, display_name)
values
  ('11111111-1111-1111-1111-111111111111', '+260971000001', 'Owner User'),
  ('22222222-2222-2222-2222-222222222222', '+260971000002', 'Other User'),
  ('33333333-3333-3333-3333-333333333333', '+260971000003', 'Admin User');

insert into public.user_roles (user_id, role)
values
  ('11111111-1111-1111-1111-111111111111', 'customer'),
  ('11111111-1111-1111-1111-111111111111', 'vendor'),
  ('22222222-2222-2222-2222-222222222222', 'customer'),
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
    'active-shop',
    'Active Shop',
    'active',
    2
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '11111111-1111-1111-1111-111111111111',
    'draft-shop',
    'Draft Shop',
    'draft',
    null
  );

insert into public.vendor_locations (id, vendor_id, lat, lng, landmark)
values
  (
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    -15.4167,
    28.2833,
    'East Park Mall'
  );

insert into public.kyc_records (id, vendor_id, tier, doc_storage_paths, status)
values
  (
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    2,
    array['private/kyc/owner/nrc-front.jpg'],
    'pending'
  );

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
-- has_role helper
-- ---------------------------------------------------------------------------

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.ok(public.has_role('admin'), 'admin user has admin role');
select extensions.ok(not public.has_role('vendor'), 'admin user is not a vendor role holder');

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.ok(not public.has_role('admin'), 'owner does not have admin role');
select extensions.ok(public.has_role('vendor'), 'owner has vendor role');

-- ---------------------------------------------------------------------------
-- profiles matrix
-- ---------------------------------------------------------------------------

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.profiles
    where id = '11111111-1111-1111-1111-111111111111'
  ),
  1,
  'owner can select own profile'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (
    select count(*)::int
    from public.profiles
    where id = '11111111-1111-1111-1111-111111111111'
  ),
  0,
  'other authed user cannot select owner profile'
);

select pg_temp.set_anon();
select extensions.is((select count(*)::int from public.profiles), 0, 'anon cannot read profiles');

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
update public.profiles
set display_name = 'Owner Updated'
where id = '11111111-1111-1111-1111-111111111111';
select extensions.is(
  (
    select display_name
    from public.profiles
    where id = '11111111-1111-1111-1111-111111111111'
  ),
  'Owner Updated',
  'owner can update own profile display_name'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$update public.profiles set deleted_at = timezone('utc', now()) where id = '11111111-1111-1111-1111-111111111111'$$,
  'P0001'
);

-- ---------------------------------------------------------------------------
-- user_roles escalation guard
-- ---------------------------------------------------------------------------

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.user_roles (user_id, role) values ('11111111-1111-1111-1111-111111111111', 'admin')$$,
  '42501'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is((select count(*)::int from public.user_roles), 0, 'authed user cannot read user_roles');

-- ---------------------------------------------------------------------------
-- vendors matrix
-- ---------------------------------------------------------------------------

select pg_temp.set_anon();
select extensions.is(
  (
    select count(*)::int
    from public.vendors
    where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  ),
  1,
  'anon can read active vendor'
);
select extensions.is(
  (
    select count(*)::int
    from public.vendors
    where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
  ),
  0,
  'anon cannot read draft vendor'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (
    select count(*)::int
    from public.vendors
    where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
  ),
  0,
  'other authed user cannot read draft vendor'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.vendors
    where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
  ),
  1,
  'owner can read own draft vendor'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
update public.vendors
set display_name = 'Active Shop Updated'
where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
select extensions.is(
  (
    select display_name
    from public.vendors
    where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  ),
  'Active Shop Updated',
  'owner can update vendor display fields'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$update public.vendors set status = 'suspended' where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'$$,
  'P0001'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$update public.vendors set kyc_tier = 3 where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'$$,
  'P0001'
);

-- ---------------------------------------------------------------------------
-- vendor_locations matrix
-- ---------------------------------------------------------------------------

select pg_temp.set_anon();
select extensions.is(
  (
    select count(*)::int
    from public.vendor_locations
    where id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
  ),
  1,
  'anon can read location for active vendor'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (
    select count(*)::int
    from public.vendor_locations vl
    join public.vendors v on v.id = vl.vendor_id
    where v.id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
  ),
  0,
  'other user cannot read draft vendor locations'
);

-- ---------------------------------------------------------------------------
-- kyc_records matrix
-- ---------------------------------------------------------------------------

select pg_temp.set_anon();
select extensions.is((select count(*)::int from public.kyc_records), 0, 'anon cannot read kyc_records');

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (
    select count(*)::int
    from public.kyc_records
    where id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
  ),
  0,
  'other authed user cannot read owner kyc_records'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.kyc_records
    where id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
  ),
  1,
  'owner can read own kyc_records'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.kyc_records (vendor_id, tier, status) values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 1, 'pending')$$,
  '42501'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.is(
  (
    select count(*)::int
    from public.kyc_records
    where id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
  ),
  1,
  'admin can read kyc_records'
);

select * from extensions.finish();
rollback;
