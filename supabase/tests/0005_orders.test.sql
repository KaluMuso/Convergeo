-- M03-P04 orders spine — RLS denial matrix, audit trigger, FK, EXPLAIN index checks
-- Requires migrations 0001–0008 applied.

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

select extensions.plan(17);

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

-- customer A
select pg_temp.seed_auth_user(
  '11111111-1111-1111-1111-111111111111',
  'customer-a@test.local'
);
-- customer B
select pg_temp.seed_auth_user(
  '22222222-2222-2222-2222-222222222222',
  'customer-b@test.local'
);
-- vendor A owner
select pg_temp.seed_auth_user(
  '33333333-3333-3333-3333-333333333333',
  'vendor-a@test.local'
);
-- vendor B owner
select pg_temp.seed_auth_user(
  '44444444-4444-4444-4444-444444444444',
  'vendor-b@test.local'
);
-- stranger
select pg_temp.seed_auth_user(
  '55555555-5555-5555-5555-555555555555',
  'stranger@test.local'
);

insert into public.profiles (id, phone, display_name)
values
  ('11111111-1111-1111-1111-111111111111', '+260971000001', 'Customer A'),
  ('22222222-2222-2222-2222-222222222222', '+260971000002', 'Customer B'),
  ('33333333-3333-3333-3333-333333333333', '+260971000003', 'Vendor A'),
  ('44444444-4444-4444-4444-444444444444', '+260971000004', 'Vendor B'),
  ('55555555-5555-5555-5555-555555555555', '+260971000005', 'Stranger');

insert into public.user_roles (user_id, role)
values
  ('11111111-1111-1111-1111-111111111111', 'customer'),
  ('22222222-2222-2222-2222-222222222222', 'customer'),
  ('33333333-3333-3333-3333-333333333333', 'vendor'),
  ('44444444-4444-4444-4444-444444444444', 'vendor'),
  ('55555555-5555-5555-5555-555555555555', 'customer');

insert into public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
values
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '33333333-3333-3333-3333-333333333333',
    'shop-a',
    'Shop A',
    'active',
    2
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '44444444-4444-4444-4444-444444444444',
    'shop-b',
    'Shop B',
    'active',
    2
  );

insert into public.categories (id, name, slug, path, commission_key)
values (
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'Electronics',
  'electronics',
  'electronics',
  'electronics'
);

insert into public.products (id, name, slug, category_id, status)
values (
  'dddddddd-dddd-dddd-dddd-dddddddddddd',
  'Test Phone',
  'test-phone',
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'active'
);

insert into public.vendor_listings (
  id,
  vendor_id,
  product_id,
  title_override,
  price_ngwee,
  condition,
  stock_mode,
  stock_qty,
  status
)
values (
  '10101010-1010-1010-1010-101010101010',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'dddddddd-dddd-dddd-dddd-dddddddddddd',
  'Phone Listing A',
  250000,
  'new',
  'tracked',
  10,
  'active'
);

insert into public.events (id, organiser_vendor_id, title, slug, status)
values (
  '20202020-2020-2020-2020-202020202020',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Gig',
  'gig',
  'published'
);

insert into public.event_instances (id, event_id, starts_at, capacity)
values (
  '30303030-3030-3030-3030-303030303030',
  '20202020-2020-2020-2020-202020202020',
  timezone('utc', now()) + interval '7 days',
  100
);

insert into public.ticket_types (id, event_id, kind, name, price_ngwee)
values (
  '40404040-4040-4040-4040-404040404040',
  '20202020-2020-2020-2020-202020202020',
  'fixed',
  'GA',
  50000
);

insert into public.addresses (id, user_id, label, landmark, phone)
values (
  '50505050-5050-5050-5050-505050505050',
  '11111111-1111-1111-1111-111111111111',
  'Home',
  'Near Manda Hill',
  '+260971000001'
);

insert into public.checkout_groups (
  id,
  customer_id,
  idempotency_key,
  subtotal_ngwee,
  delivery_fee_ngwee,
  total_ngwee,
  status
)
values (
  '60606060-6060-6060-6060-606060606060',
  '11111111-1111-1111-1111-111111111111',
  'idem-customer-a-001',
  250000,
  3000,
  253000,
  'pending'
);

insert into public.orders (
  id,
  checkout_group_id,
  vendor_id,
  customer_id,
  status,
  fulfilment,
  delivery_zone,
  address_id,
  delivery_fee_ngwee,
  cod,
  commission_snapshot
)
values
  (
    '70707070-7070-7070-7070-707070707070',
    '60606060-6060-6060-6060-606060606060',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'placed',
    'delivery',
    'lusaka_a',
    '50505050-5050-5050-5050-505050505050',
    3000,
    false,
  '{"rate_bps": 500}'::jsonb
  ),
  (
    '80808080-8080-8080-8080-808080808080',
    '60606060-6060-6060-6060-606060606060',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '11111111-1111-1111-1111-111111111111',
    'placed',
    'pickup',
    null,
    null,
    0,
    false,
    '{}'::jsonb
  );

insert into public.checkout_groups (
  id,
  customer_id,
  idempotency_key,
  subtotal_ngwee,
  delivery_fee_ngwee,
  total_ngwee,
  status
)
values (
  '90909090-9090-9090-9090-909090909090',
  '22222222-2222-2222-2222-222222222222',
  'idem-customer-b-001',
  100000,
  0,
  100000,
  'pending'
);

insert into public.orders (
  id,
  checkout_group_id,
  vendor_id,
  customer_id,
  status,
  fulfilment,
  delivery_fee_ngwee
)
values (
  'a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0',
  '90909090-9090-9090-9090-909090909090',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '22222222-2222-2222-2222-222222222222',
  'placed',
  'pickup',
  0
);

insert into public.order_items (
  id,
  order_id,
  item_kind,
  qty,
  unit_price_ngwee,
  title_snapshot
)
values (
  'b0b0b0b0-b0b0-b0b0-b0b0-b0b0b0b0b0b0',
  '70707070-7070-7070-7070-707070707070',
  'product',
  1,
  250000,
  'Phone Listing A'
);

insert into public.order_item_products (order_item_id, listing_id, product_id)
values (
  'b0b0b0b0-b0b0-b0b0-b0b0-b0b0b0b0b0b0',
  '10101010-1010-1010-1010-101010101010',
  'dddddddd-dddd-dddd-dddd-dddddddddddd'
);

insert into public.stock_reservations (
  id,
  listing_id,
  checkout_group_id,
  qty,
  expires_at
)
values (
  'c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0',
  '10101010-1010-1010-1010-101010101010',
  '60606060-6060-6060-6060-606060606060',
  1,
  timezone('utc', now()) + interval '15 minutes'
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

-- ---------------------------------------------------------------------------
-- Idempotency + tickets FK (constraints)
-- ---------------------------------------------------------------------------

select extensions.throws_ok(
  $$insert into public.checkout_groups (
      customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
    ) values (
      '11111111-1111-1111-1111-111111111111', 'idem-customer-a-001', 1, 0, 1
    )$$,
  '23505',
  null,
  'duplicate idempotency_key rejected'
);

select extensions.throws_ok(
  $$insert into public.tickets (
      instance_id,
      ticket_type_id,
      holder_user_id,
      order_item_id,
      qr_secret,
      pin_hash
    ) values (
      '30303030-3030-3030-3030-303030303030',
      '40404040-4040-4040-4040-404040404040',
      '11111111-1111-1111-1111-111111111111',
      '00000000-0000-0000-0000-000000000001',
      'qr',
      'pin'
    )$$,
  '23503',
  null,
  'tickets.order_item_id FK enforced'
);

-- ---------------------------------------------------------------------------
-- Audit trigger via service_role status change
-- ---------------------------------------------------------------------------

select extensions.is(
  (
    select count(*)::int
    from public.order_events
    where order_id = '70707070-7070-7070-7070-707070707070'
  ),
  0,
  'no audit rows before status change'
);

update public.orders
set status = 'confirmed'
where id = '70707070-7070-7070-7070-707070707070';

select extensions.is(
  (
    select count(*)::int
    from public.order_events
    where order_id = '70707070-7070-7070-7070-707070707070'
  ),
  1,
  'status change writes one audit row'
);

select extensions.is(
  (
    select from_status
    from public.order_events
    where order_id = '70707070-7070-7070-7070-707070707070'
    order by created_at desc
    limit 1
  ),
  'placed',
  'audit from_status captured'
);

select extensions.is(
  (
    select to_status
    from public.order_events
    where order_id = '70707070-7070-7070-7070-707070707070'
    order by created_at desc
    limit 1
  ),
  'confirmed',
  'audit to_status captured'
);

-- ---------------------------------------------------------------------------
-- RLS matrix (non-superuser)
-- ---------------------------------------------------------------------------

set session authorization vergeo_rls_tester;

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (
    select count(*)::int
    from public.orders
    where customer_id = '11111111-1111-1111-1111-111111111111'
  ),
  2,
  'customer A sees own orders'
);
select extensions.is(
  (
    select count(*)::int
    from public.orders
    where customer_id = '22222222-2222-2222-2222-222222222222'
  ),
  0,
  'customer A cannot see customer B orders'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.is(
  (
    select count(*)::int
    from public.orders
    where vendor_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  ),
  2,
  'vendor A sees own-vendor orders'
);
select extensions.is(
  (
    select count(*)::int
    from public.orders
    where vendor_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
  ),
  0,
  'vendor A cannot see vendor B orders'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.is(
  (select count(*)::int from public.order_items),
  0,
  'stranger sees no order_items'
);

-- Must-pass: client status UPDATE denied (customer + vendor)
select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
update public.orders
set status = 'cancelled'
where id = '80808080-8080-8080-8080-808080808080';
select extensions.is(
  (
    select status
    from public.orders
    where id = '80808080-8080-8080-8080-808080808080'
  ),
  'placed',
  'customer status UPDATE denied'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
update public.orders
set status = 'processing'
where id = '70707070-7070-7070-7070-707070707070';
select extensions.is(
  (
    select status
    from public.orders
    where id = '70707070-7070-7070-7070-707070707070'
  ),
  'confirmed',
  'vendor status UPDATE denied'
);

-- Client insert denied
select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.checkout_groups (
      customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
    ) values (
      '11111111-1111-1111-1111-111111111111', 'client-attempt', 1, 0, 1
    )$$,
  '42501',
  null,
  'client checkout_groups insert denied'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.stock_reservations (
      listing_id, checkout_group_id, qty, expires_at
    ) values (
      '10101010-1010-1010-1010-101010101010',
      '60606060-6060-6060-6060-606060606060',
      1,
      timezone('utc', now()) + interval '10 minutes'
    )$$,
  '42501',
  null,
  'client stock_reservations insert denied'
);

reset session authorization;

-- ---------------------------------------------------------------------------
-- EXPLAIN index checks (hot paths)
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
    from public.orders
    where vendor_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
      and status = 'confirmed'
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
    where plan ilike '%orders_vendor_id_status_idx%'
       or plan ilike '%Index Scan%orders%vendor_id%'
  ),
  'vendor open-orders queue uses (vendor_id, status) index'
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
    from public.stock_reservations
    where expires_at < timezone('utc', now()) + interval '1 hour'
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
    where plan ilike '%stock_reservations_expires_at_idx%'
       or plan ilike '%Index Scan%stock_reservations%expires_at%'
  ),
  'expiring reservations sweeper uses expires_at index'
);

select * from extensions.finish();
rollback;
