-- M03-P03 services & events policy smoke tests (pgTAP via `supabase test db`).

begin;

set local search_path to public, extensions, auth;

select extensions.plan(17);

-- Seed fixtures with service_role (bypasses RLS); assertions run as client roles.
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

-- customer / job owner
select pg_temp.seed_auth_user(
  '11111111-1111-1111-1111-111111111111',
  'customer@test.local'
);
-- stranger
select pg_temp.seed_auth_user(
  '22222222-2222-2222-2222-222222222222',
  'stranger@test.local'
);
-- provider A owner
select pg_temp.seed_auth_user(
  '33333333-3333-3333-3333-333333333333',
  'provider-a@test.local'
);
-- provider B owner
select pg_temp.seed_auth_user(
  '44444444-4444-4444-4444-444444444444',
  'provider-b@test.local'
);
-- ticket holder
select pg_temp.seed_auth_user(
  '55555555-5555-5555-5555-555555555555',
  'holder@test.local'
);
-- admin
select pg_temp.seed_auth_user(
  '66666666-6666-6666-6666-666666666666',
  'admin@test.local'
);

insert into public.profiles (id, phone, display_name)
values
  ('11111111-1111-1111-1111-111111111111', '+260971000001', 'Customer'),
  ('22222222-2222-2222-2222-222222222222', '+260971000002', 'Stranger'),
  ('33333333-3333-3333-3333-333333333333', '+260971000003', 'Provider A'),
  ('44444444-4444-4444-4444-444444444444', '+260971000004', 'Provider B'),
  ('55555555-5555-5555-5555-555555555555', '+260971000005', 'Holder'),
  ('66666666-6666-6666-6666-666666666666', '+260971000006', 'Admin');

insert into public.user_roles (user_id, role)
values
  ('11111111-1111-1111-1111-111111111111', 'customer'),
  ('22222222-2222-2222-2222-222222222222', 'customer'),
  ('33333333-3333-3333-3333-333333333333', 'vendor'),
  ('44444444-4444-4444-4444-444444444444', 'vendor'),
  ('55555555-5555-5555-5555-555555555555', 'customer'),
  ('66666666-6666-6666-6666-666666666666', 'admin');

insert into public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
values
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '33333333-3333-3333-3333-333333333333',
    'provider-a',
    'Provider A Shop',
    'active',
    2
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '44444444-4444-4444-4444-444444444444',
    'provider-b',
    'Provider B Shop',
    'active',
    2
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    '33333333-3333-3333-3333-333333333333',
    'events-co',
    'Events Co',
    'active',
    2
  );

insert into public.jobs (id, customer_id, category, description, status)
values (
  'dddddddd-dddd-dddd-dddd-dddddddddddd',
  '11111111-1111-1111-1111-111111111111',
  'plumbing',
  'Fix kitchen sink',
  'open'
);

insert into public.job_quotes (
  id,
  job_id,
  provider_vendor_id,
  amount_ngwee,
  message,
  status
)
values
  (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    150000,
    'Provider A quote',
    'submitted'
  ),
  (
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    120000,
    'Provider B quote',
    'submitted'
  );

insert into public.events (id, organiser_vendor_id, title, slug, status)
values
  (
    '10101010-1010-1010-1010-101010101010',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    'Draft Gig',
    'draft-gig',
    'draft'
  ),
  (
    '20202020-2020-2020-2020-202020202020',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    'Published Gig',
    'published-gig',
    'published'
  );

insert into public.event_instances (id, event_id, starts_at, capacity)
values
  (
    '30303030-3030-3030-3030-303030303030',
    '20202020-2020-2020-2020-202020202020',
    timezone('utc', now()) + interval '7 days',
    100
  );

insert into public.ticket_types (id, event_id, kind, name, price_ngwee)
values
  (
    '40404040-4040-4040-4040-404040404040',
    '20202020-2020-2020-2020-202020202020',
    'fixed',
    'General Admission',
    50000
  ),
  (
    '50505050-5050-5050-5050-505050505050',
    '20202020-2020-2020-2020-202020202020',
    'free_rsvp',
    'Free RSVP',
    0
  );

insert into public.tickets (
  id,
  instance_id,
  ticket_type_id,
  holder_user_id,
  status,
  qr_secret,
  pin_hash
)
values (
  '60606060-6060-6060-6060-606060606060',
  '30303030-3030-3030-3030-303030303030',
  '40404040-4040-4040-4040-404040404040',
  '55555555-5555-5555-5555-555555555555',
  'issued',
  'super-secret-qr',
  'hashed-pin-value'
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
-- Quote privacy matrix (must-pass)
-- ---------------------------------------------------------------------------

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.is(
  (
    select count(*)::int
    from public.job_quotes
    where id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  ),
  1,
  'provider A can read own quote'
);
select extensions.is(
  (
    select count(*)::int
    from public.job_quotes
    where id = 'ffffffff-ffff-ffff-ffff-ffffffffffff'
  ),
  0,
  'provider A cannot read provider B quote on same job'
);

select pg_temp.set_auth('44444444-4444-4444-4444-444444444444');
select extensions.is(
  (
    select count(*)::int
    from public.job_quotes
    where id = 'ffffffff-ffff-ffff-ffff-ffffffffffff'
  ),
  1,
  'provider B can read own quote'
);
select extensions.is(
  (
    select count(*)::int
    from public.job_quotes
    where id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
  ),
  0,
  'provider B cannot read provider A quote on same job'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.job_quotes
    where job_id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
  ),
  2,
  'job customer sees all quotes on own job'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (select count(*)::int from public.job_quotes),
  0,
  'stranger sees no quotes'
);

-- ---------------------------------------------------------------------------
-- Events visibility
-- ---------------------------------------------------------------------------

select pg_temp.set_anon();
select extensions.is(
  (
    select count(*)::int
    from public.events
    where id = '10101010-1010-1010-1010-101010101010'
  ),
  0,
  'anon cannot read draft event'
);
select extensions.is(
  (
    select count(*)::int
    from public.events
    where id = '20202020-2020-2020-2020-202020202020'
  ),
  1,
  'anon can read published event'
);

-- ---------------------------------------------------------------------------
-- Ticket visibility + secrets
-- ---------------------------------------------------------------------------

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.is(
  (
    select qr_secret
    from public.tickets
    where id = '60606060-6060-6060-6060-606060606060'
  ),
  'super-secret-qr',
  'holder can read ticket including qr_secret'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.is(
  (
    select pin_hash
    from public.tickets
    where id = '60606060-6060-6060-6060-606060606060'
  ),
  'hashed-pin-value',
  'organiser can read ticket secrets for check-in'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (
    select count(*)::int
    from public.tickets
    where id = '60606060-6060-6060-6060-606060606060'
  ),
  0,
  'third authenticated user cannot read ticket'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.throws_ok(
  $$insert into public.tickets (
      instance_id,
      ticket_type_id,
      holder_user_id,
      qr_secret,
      pin_hash
    ) values (
      '30303030-3030-3030-3030-303030303030',
      '40404040-4040-4040-4040-404040404040',
      '55555555-5555-5555-5555-555555555555',
      'nope',
      'nope'
    )$$,
  NULL,
  NULL,
  'client ticket insert denied'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
update public.tickets
set status = 'checked_in'
where id = '60606060-6060-6060-6060-606060606060';
select extensions.is(
  (
    select status
    from public.tickets
    where id = '60606060-6060-6060-6060-606060606060'
  ),
  'issued',
  'client ticket status flip denied'
);

-- ---------------------------------------------------------------------------
-- ticket_types price constraints
-- ---------------------------------------------------------------------------

set local role service_role;

select extensions.throws_ok(
  $$insert into public.ticket_types (event_id, kind, name, price_ngwee)
    values ('20202020-2020-2020-2020-202020202020', 'fixed', 'Bad Zero', 0)$$,
  '23514'
);

select extensions.lives_ok(
  $$insert into public.ticket_types (id, event_id, kind, name, price_ngwee)
    values (
      '70707070-7070-7070-7070-707070707070',
      '20202020-2020-2020-2020-202020202020',
      'free_rsvp',
      'Another Free RSVP',
      0
    )$$,
  'price_ngwee=0 accepted for kind=free_rsvp'
);

select extensions.throws_ok(
  $$insert into public.ticket_types (event_id, kind, name, price_ngwee)
    values ('20202020-2020-2020-2020-202020202020', 'free_rsvp', 'Bad Paid', 1000)$$,
  '23514'
);

-- ---------------------------------------------------------------------------
-- event_instances capacity NOT NULL enforced at DDL (smoke)
-- ---------------------------------------------------------------------------

select extensions.throws_ok(
  $$insert into public.event_instances (event_id, starts_at, capacity)
    values ('20202020-2020-2020-2020-202020202020', timezone('utc', now()), null)$$,
  '23502'
);

select * from extensions.finish();
rollback;
