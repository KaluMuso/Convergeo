-- M03-P06 trust & ops schema — verified-purchase reviews, outbox/audit RLS, disputes, EXPLAIN
-- Requires migrations 0001–0010 applied.

begin;

set local search_path to public, extensions, auth;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'vergeo_rls_tester') then
    create role vergeo_rls_tester login password 'test' nosuperuser nobypassrls;
    grant authenticated to vergeo_rls_tester;
    grant anon to vergeo_rls_tester;
  end if;
  grant usage on schema extensions to vergeo_rls_tester;
  grant execute on all functions in schema extensions to vergeo_rls_tester;
end;
$$;

grant all on table auth.users to service_role;
grant usage on schema public, auth, extensions to vergeo_rls_tester, service_role;
grant all on all tables in schema public to vergeo_rls_tester, service_role;
grant execute on all functions in schema public to vergeo_rls_tester, service_role;
grant execute on all functions in schema extensions to vergeo_rls_tester, service_role;

select extensions.plan(14);

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
  'customer-a@test.local'
);
select pg_temp.seed_auth_user(
  '22222222-2222-2222-2222-222222222222',
  'customer-b@test.local'
);
select pg_temp.seed_auth_user(
  '33333333-3333-3333-3333-333333333333',
  'vendor-a@test.local'
);
select pg_temp.seed_auth_user(
  '55555555-5555-5555-5555-555555555555',
  'stranger@test.local'
);

-- 0010 trigger auto-creates profiles + customer role on auth.users insert.
update public.profiles
set phone = '+260971000001', display_name = 'Customer A'
where id = '11111111-1111-1111-1111-111111111111';

update public.profiles
set phone = '+260971000002', display_name = 'Customer B'
where id = '22222222-2222-2222-2222-222222222222';

update public.profiles
set phone = '+260971000003', display_name = 'Vendor A'
where id = '33333333-3333-3333-3333-333333333333';

update public.profiles
set phone = '+260971000005', display_name = 'Stranger'
where id = '55555555-5555-5555-5555-555555555555';

insert into public.user_roles (user_id, role)
values ('33333333-3333-3333-3333-333333333333', 'vendor')
on conflict do nothing;

insert into public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '33333333-3333-3333-3333-333333333333',
  'shop-a',
  'Shop A',
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
  'idem-trust-a-001',
  250000,
  0,
  250000,
  'completed'
);

-- delivered order (customer A) — eligible for review
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
  '70707070-7070-7070-7070-707070707070',
  '60606060-6060-6060-6060-606060606060',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
  'delivered',
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

-- placed order (customer A) — not eligible for review
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
  '80808080-8080-8080-8080-808080808080',
  '11111111-1111-1111-1111-111111111111',
  'idem-trust-a-002',
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
  '90909090-9090-9090-9090-909090909090',
  '80808080-8080-8080-8080-808080808080',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
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
  'c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0',
  '90909090-9090-9090-9090-909090909090',
  'product',
  1,
  100000,
  'Phone Listing A'
);

insert into public.order_item_products (order_item_id, listing_id, product_id)
values (
  'c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0',
  '10101010-1010-1010-1010-101010101010',
  'dddddddd-dddd-dddd-dddd-dddddddddddd'
);

-- customer B delivered order on same listing (for stranger/non-owner tests)
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
  'a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0',
  '22222222-2222-2222-2222-222222222222',
  'idem-trust-b-001',
  250000,
  0,
  250000,
  'completed'
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
  'b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1',
  'a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '22222222-2222-2222-2222-222222222222',
  'completed',
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
  'd0d0d0d0-d0d0-d0d0-d0d0-d0d0d0d0d0d0',
  'b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1',
  'product',
  1,
  250000,
  'Phone Listing A'
);

insert into public.order_item_products (order_item_id, listing_id, product_id)
values (
  'd0d0d0d0-d0d0-d0d0-d0d0-d0d0d0d0d0d0',
  '10101010-1010-1010-1010-101010101010',
  'dddddddd-dddd-dddd-dddd-dddddddddddd'
);

insert into public.notification_outbox (
  id,
  dedupe_key,
  channel,
  template,
  payload,
  status,
  next_retry_at
)
values (
  'e0e0e0e0-e0e0-e0e0-e0e0-e0e0e0e0e0e0',
  'order.delivered:70707070-7070-7070-7070-707070707070:whatsapp',
  'whatsapp',
  'order_delivered',
  '{"order_id":"70707070-7070-7070-7070-707070707070"}'::jsonb,
  'pending',
  timezone('utc', now())
);

insert into public.audit_log (id, actor, action, entity_type, entity_id, before, after)
values (
  'f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0',
  '11111111-1111-1111-1111-111111111111',
  'flag_review',
  'review',
  '00000000-0000-0000-0000-000000000001',
  null,
  '{"status":"flagged"}'::jsonb
);

insert into public.reviews (
  id,
  order_item_id,
  rating,
  body,
  status
)
values (
  '11111111-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'b0b0b0b0-b0b0-b0b0-b0b0-b0b0b0b0b0b0',
  5,
  'Great phone!',
  'published'
);

-- second delivered order_item for customer B (no review yet — used for verified insert test)
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
  'c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1',
  '22222222-2222-2222-2222-222222222222',
  'idem-trust-b-002',
  150000,
  0,
  150000,
  'completed'
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
  'c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2',
  'c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '22222222-2222-2222-2222-222222222222',
  'delivered',
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
  'e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1',
  'c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2',
  'product',
  1,
  150000,
  'Phone Listing A'
);

insert into public.order_item_products (order_item_id, listing_id, product_id)
values (
  'e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1',
  '10101010-1010-1010-1010-101010101010',
  'dddddddd-dddd-dddd-dddd-dddddddddddd'
);

insert into public.reviews (
  id,
  order_item_id,
  rating,
  body,
  status
)
values (
  '22222222-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'd0d0d0d0-d0d0-d0d0-d0d0-d0d0d0d0d0d0',
  3,
  'Flagged review',
  'flagged'
);

insert into public.disputes (
  id,
  order_id,
  opener_user_id,
  status
)
values (
  '33333333-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '70707070-7070-7070-7070-707070707070',
  '11111111-1111-1111-1111-111111111111',
  'open'
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
-- Constraint checks (service_role / unique)
-- ---------------------------------------------------------------------------

select extensions.throws_ok(
  $$insert into public.notification_outbox (dedupe_key, channel, template)
    values (
      'order.delivered:70707070-7070-7070-7070-707070707070:whatsapp',
      'email',
      'order_delivered'
    )$$,
  '23505',
  null,
  'notification_outbox dedupe_key unique enforced'
);

-- ---------------------------------------------------------------------------
-- RLS matrix (non-superuser)
-- ---------------------------------------------------------------------------

set session authorization vergeo_rls_tester;

-- Verified-purchase trigger + unique (must run as non-superuser)
select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');

select extensions.throws_ok(
  $$insert into public.reviews (order_item_id, rating, body)
    values ('c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0', 4, 'too early')$$,
  'P0001',
  null,
  'non-delivered order_item review denied by trigger'
);

select extensions.throws_ok(
  $$insert into public.reviews (order_item_id, rating, body)
    values ('b0b0b0b0-b0b0-b0b0-b0b0-b0b0b0b0b0b0', 2, 'duplicate')$$,
  '23505',
  null,
  'double review on same order_item denied by unique constraint'
);

-- Verified path: customer B inserts review on their delivered item (no prior review)
select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');

select extensions.lives_ok(
  $$insert into public.reviews (order_item_id, rating, body)
    values ('e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1', 4, 'Verified purchase review')$$,
  'verified-purchase review insert succeeds for order owner'
);

-- Non-owner insert denied (RLS + trigger)
select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');

select extensions.throws_ok(
  $$insert into public.reviews (order_item_id, rating, body)
    values ('b0b0b0b0-b0b0-b0b0-b0b0-b0b0b0b0b0b0', 1, 'fake')$$,
  'P0001',
  null,
  'stranger review insert denied'
);

-- Public reads only published reviews
select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');

select extensions.is(
  (select count(*)::int from public.reviews),
  2,
  'public sees only published reviews (flagged hidden; includes B verified insert)'
);

-- Author blocked on non-delivered order_item (trigger; duplicate of earlier assertion)
select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');

select extensions.throws_ok(
  $$insert into public.reviews (order_item_id, rating, body)
    values ('c0c0c0c0-c0c0-c0c0-c0c0-c0c0c0c0c0c0', 5, 'not delivered again')$$,
  'P0001',
  null,
  'author blocked on non-delivered order_item'
);

-- Client cannot read outbox/audit
select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');

select extensions.throws_ok(
  $$select count(*) from public.notification_outbox$$,
  '42501',
  null,
  'client cannot read notification_outbox'
);

select extensions.throws_ok(
  $$select count(*) from public.audit_log$$,
  '42501',
  null,
  'client cannot read audit_log'
);

-- Dispute parties see own; stranger denied
select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');

select extensions.is(
  (select count(*)::int from public.disputes),
  1,
  'dispute customer party sees own dispute'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');

select extensions.is(
  (select count(*)::int from public.disputes),
  1,
  'dispute vendor party sees own dispute'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');

select extensions.is(
  (select count(*)::int from public.disputes),
  0,
  'stranger cannot see disputes'
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
  rec record;
begin
  for rec in
    explain (costs off)
    select rev.*
    from public.reviews rev
    inner join public.order_item_products oip on oip.order_item_id = rev.order_item_id
    where oip.listing_id = '10101010-1010-1010-1010-101010101010'
      and rev.status = 'published'
  loop
    plan_text := plan_text || rec."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (plan) values (plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where plan ilike '%reviews_status_order_item_id_idx%'
       or plan ilike '%Index%reviews%'
  ),
  'published-reviews-by-listing uses reviews partial index'
);

truncate explain_plans;

do $$
declare
  plan_text text := '';
  rec record;
begin
  for rec in
    explain (costs off)
    select id
    from public.notification_outbox
    where status = 'pending'
      and next_retry_at <= timezone('utc', now()) + interval '1 hour'
    order by next_retry_at
  loop
    plan_text := plan_text || rec."QUERY PLAN" || E'\n';
  end loop;
  insert into explain_plans (plan) values (plan_text);
end;
$$;

select extensions.ok(
  exists (
    select 1
    from explain_plans
    where plan ilike '%notification_outbox_status_next_retry_at_idx%'
       or plan ilike '%Index%notification_outbox%'
  ),
  'pending outbox dispatcher uses (status, next_retry_at) index'
);

select * from extensions.finish();
rollback;
