-- M04-P01 profile bootstrap — trigger idempotency on auth.users insert.
-- Run: supabase test db (or psql after supabase db reset).

begin;

set local search_path to public, extensions, auth;

select extensions.plan(6);

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

-- First signup path: trigger creates profile + customer role.
select pg_temp.seed_auth_user(
  '44444444-4444-4444-4444-444444444444',
  'bootstrap@test.local'
);

select extensions.is(
  (
    select count(*)::int
    from public.profiles
    where id = '44444444-4444-4444-4444-444444444444'
  ),
  1,
  'auth.users insert creates exactly one profile row'
);

select extensions.is(
  (
    select count(*)::int
    from public.user_roles
    where user_id = '44444444-4444-4444-4444-444444444444'
      and role = 'customer'
  ),
  1,
  'auth.users insert creates exactly one customer role row'
);

-- Idempotent re-run: manual profile/role inserts must not duplicate.
insert into public.profiles (id)
values ('44444444-4444-4444-4444-444444444444')
on conflict (id) do nothing;

insert into public.user_roles (user_id, role)
values ('44444444-4444-4444-4444-444444444444', 'customer')
on conflict (user_id, role) do nothing;

select extensions.is(
  (
    select count(*)::int
    from public.profiles
    where id = '44444444-4444-4444-4444-444444444444'
  ),
  1,
  'profile bootstrap remains idempotent (single profile row)'
);

select extensions.is(
  (
    select count(*)::int
    from public.user_roles
    where user_id = '44444444-4444-4444-4444-444444444444'
      and role = 'customer'
  ),
  1,
  'role bootstrap remains idempotent (single customer role row)'
);

-- Second distinct user still bootstraps cleanly.
select pg_temp.seed_auth_user(
  '55555555-5555-5555-5555-555555555555',
  'bootstrap2@test.local'
);

select extensions.is(
  (
    select count(*)::int
    from public.profiles
    where id = '55555555-5555-5555-5555-555555555555'
  ),
  1,
  'second auth.users insert bootstraps its own profile'
);

select extensions.is(
  (
    select count(*)::int
    from public.user_roles
    where user_id = '55555555-5555-5555-5555-555555555555'
      and role = 'customer'
  ),
  1,
  'second auth.users insert bootstraps its own customer role'
);

select * from extensions.finish();
rollback;
