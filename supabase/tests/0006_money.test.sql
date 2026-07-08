-- M03-P05 money schema — zero-sum, idempotency, invoice counter, RLS, EXPLAIN index checks
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
end;
$$;

grant all on table auth.users to service_role;
grant usage on schema public, auth, extensions to vergeo_rls_tester;
grant all on all tables in schema public to vergeo_rls_tester;
grant execute on all functions in schema public to vergeo_rls_tester;

select extensions.plan(20);

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
  '44444444-4444-4444-4444-444444444444',
  'vendor-b@test.local'
);
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
  ('55555555-5555-5555-5555-555555555555', '+260971000005', 'Stranger')
on conflict (id) do nothing;

insert into public.user_roles (user_id, role)
values
  ('11111111-1111-1111-1111-111111111111', 'customer'),
  ('22222222-2222-2222-2222-222222222222', 'customer'),
  ('33333333-3333-3333-3333-333333333333', 'vendor'),
  ('44444444-4444-4444-4444-444444444444', 'vendor'),
  ('55555555-5555-5555-5555-555555555555', 'customer')
on conflict do nothing;

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
  )
on conflict (id) do nothing;

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
  'idem-money-a-001',
  250000,
  3000,
  253000,
  'pending'
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
  'idem-money-b-001',
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
  '70707070-7070-7070-7070-707070707070',
  '60606060-6060-6060-6060-606060606060',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
  'placed',
  'pickup',
  0
);

insert into public.ledger_accounts (id, kind)
values
  ('d1111111-1111-1111-1111-111111111111', 'escrow'),
  ('d2222222-2222-2222-2222-222222222222', 'platform_cash');

insert into public.payments (
  id,
  checkout_group_id,
  provider,
  rail,
  lenco_reference,
  amount_ngwee,
  status
)
values (
  'a1111111-1111-1111-1111-111111111111',
  '60606060-6060-6060-6060-606060606060',
  'lenco',
  'mtn',
  'pay-test-001',
  253000,
  'success'
);

insert into public.payouts (
  id,
  vendor_id,
  amount_ngwee,
  rail,
  lenco_reference,
  status
)
values (
  'b1111111-1111-1111-1111-111111111111',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  200000,
  'mtn',
  'payout-test-001',
  'paid'
);

insert into public.refunds (
  id,
  order_id,
  lane,
  breakdown,
  amount_ngwee,
  status
)
values (
  'c1111111-1111-1111-1111-111111111111',
  '70707070-7070-7070-7070-707070707070',
  1,
  '{"item_ngwee": 250000}'::jsonb,
  250000,
  'pending'
);

insert into public.invoice_counters (series, next_no)
values ('ZMW', 1)
on conflict (series) do update set next_no = 1;

insert into public.invoices (
  id,
  series,
  no,
  order_id,
  snapshot
)
values (
  'e1111111-1111-1111-1111-111111111111',
  'ZMW',
  1,
  '70707070-7070-7070-7070-707070707070',
  '{"total_ngwee": 253000}'::jsonb
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
-- Zero-sum ledger trigger
-- ---------------------------------------------------------------------------

select extensions.lives_ok(
  $$
  do $inner$
  declare
    v_txn uuid;
  begin
    insert into public.ledger_transactions (kind)
    values ('payment_captured')
    returning id into v_txn;

    insert into public.ledger_postings (transaction_id, account_id, amount_ngwee)
    values
      (v_txn, 'd1111111-1111-1111-1111-111111111111', 253000),
      (v_txn, 'd2222222-2222-2222-2222-222222222222', -253000);

    set constraints ledger_postings_zero_sum immediate;
  end;
  $inner$;
  $$,
  'balanced ledger postings accepted at commit'
);

select extensions.throws_ok(
  $$
  do $inner$
  declare
    v_txn uuid;
  begin
    insert into public.ledger_transactions (kind)
    values ('payment_captured')
    returning id into v_txn;

    insert into public.ledger_postings (transaction_id, account_id, amount_ngwee)
    values (v_txn, 'd1111111-1111-1111-1111-111111111111', 100000);

    set constraints ledger_postings_zero_sum immediate;
  end;
  $inner$;
  $$,
  '23514',
  null,
  'unbalanced ledger transaction rejected at commit'
);

-- ---------------------------------------------------------------------------
-- Webhook + lenco_reference uniqueness / charset
-- ---------------------------------------------------------------------------

insert into public.webhook_events (provider, event_id, signature_valid)
values ('lenco', 'evt-dup-001', true);

select extensions.throws_ok(
  $$insert into public.webhook_events (provider, event_id, signature_valid)
    values ('lenco', 'evt-dup-001', true)$$,
  '23505',
  null,
  'duplicate webhook (provider, event_id) rejected'
);

select extensions.throws_ok(
  $$insert into public.webhook_events (provider, event_id, signature_valid)
    values ('lenco', 'evt-dup-001', true)$$,
  '23505',
  null,
  'duplicate webhook replay rejected'
);

select extensions.throws_ok(
  $$insert into public.payments (
      checkout_group_id, provider, rail, lenco_reference, amount_ngwee
    ) values (
      '60606060-6060-6060-6060-606060606060',
      'lenco', 'mtn', 'pay-test-001', 1000
    )$$,
  '23505',
  null,
  'duplicate lenco_reference rejected'
);

select extensions.throws_ok(
  $$insert into public.payments (
      checkout_group_id, provider, rail, lenco_reference, amount_ngwee
    ) values (
      '90909090-9090-9090-9090-909090909090',
      'lenco', 'mtn', 'pay/bad!', 1000
    )$$,
  '23514',
  null,
  'bad-charset lenco_reference rejected'
);

-- ---------------------------------------------------------------------------
-- Gapless invoice counter (serialized next_invoice_no)
-- ---------------------------------------------------------------------------

update public.invoice_counters set next_no = 10 where series = 'ZMW';

select extensions.is(
  public.next_invoice_no('ZMW'),
  10::bigint,
  'first next_invoice_no returns locked value'
);

select extensions.is(
  public.next_invoice_no('ZMW'),
  11::bigint,
  'second next_invoice_no returns consecutive value (no gap)'
);

select extensions.is(
  (select next_no from public.invoice_counters where series = 'ZMW'),
  12::bigint,
  'counter advanced to next slot after two allocations'
);

-- ---------------------------------------------------------------------------
-- RLS matrix (non-superuser)
-- ---------------------------------------------------------------------------

set session authorization vergeo_rls_tester;

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (select count(*)::int from public.payments),
  1,
  'customer A reads own payment via checkout_group'
);

select pg_temp.set_auth('22222222-2222-2222-2222-222222222222');
select extensions.is(
  (select count(*)::int from public.payments),
  0,
  'customer B cannot read customer A payment'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.is(
  (select count(*)::int from public.payouts),
  1,
  'vendor A reads own payout'
);

select pg_temp.set_auth('44444444-4444-4444-4444-444444444444');
select extensions.is(
  (select count(*)::int from public.payouts),
  0,
  'vendor B cannot read vendor A payout'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (select count(*)::int from public.refunds),
  1,
  'customer reads own refund'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (select count(*)::int from public.invoices),
  1,
  'customer reads own invoice'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.is(
  (select count(*)::int from public.ledger_accounts),
  0,
  'stranger cannot read ledger_accounts'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (select count(*)::int from public.webhook_events),
  0,
  'customer cannot read webhook_events'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.payments (
      checkout_group_id, provider, rail, lenco_reference, amount_ngwee
    ) values (
      '60606060-6060-6060-6060-606060606060',
      'lenco', 'mtn', 'pay-client-attempt', 1000
    )$$,
  '42501',
  null,
  'client payment insert denied'
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
    from public.payments
    where checkout_group_id = '60606060-6060-6060-6060-606060606060'
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
    where plan ilike '%payments_checkout_group_id_idx%'
       or plan ilike '%Index Scan%payments%checkout_group_id%'
  ),
  'payments-by-checkout-group uses checkout_group_id index'
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
    from public.payouts
    where vendor_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
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
    where plan ilike '%payouts_vendor_id_idx%'
       or plan ilike '%Index Scan%payouts%vendor_id%'
  ),
  'payouts-by-vendor uses vendor_id index'
);

select * from extensions.finish();
rollback;
