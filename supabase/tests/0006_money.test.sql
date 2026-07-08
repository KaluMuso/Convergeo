-- M03-P05 money schema — zero-sum ledger, webhook/reference uniqueness, invoice concurrency, RLS, EXPLAIN.
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

select extensions.plan(24);

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

insert into public.user_roles (user_id, role)
values
  ('33333333-3333-3333-3333-333333333333', 'vendor'),
  ('44444444-4444-4444-4444-444444444444', 'vendor')
on conflict (user_id, role) do nothing;

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

insert into public.checkout_groups (
  id,
  customer_id,
  idempotency_key,
  subtotal_ngwee,
  delivery_fee_ngwee,
  total_ngwee,
  status
)
values
  (
    '60606060-6060-6060-6060-606060606060',
    '11111111-1111-1111-1111-111111111111',
    'idem-money-a',
    250000,
    3000,
    253000,
    'pending'
  ),
  (
    '90909090-9090-9090-9090-909090909090',
    '22222222-2222-2222-2222-222222222222',
    'idem-money-b',
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
values
  (
    '70707070-7070-7070-7070-707070707070',
    '60606060-6060-6060-6060-606060606060',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'placed',
    'pickup',
    0
  ),
  (
    'a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0',
    '90909090-9090-9090-9090-909090909090',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '22222222-2222-2222-2222-222222222222',
    'placed',
    'pickup',
    0
  );

insert into public.ledger_accounts (id, kind)
values
  ('e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1', 'escrow'),
  ('e2e2e2e2-e2e2-e2e2-e2e2-e2e2e2e2e2e2', 'platform_cash');

insert into public.payments (
  id,
  checkout_group_id,
  provider,
  rail,
  lenco_reference,
  amount_ngwee,
  status
)
values
  (
    'f1f1f1f1-f1f1-f1f1-f1f1-f1f1f1f1f1f1',
    '60606060-6060-6060-6060-606060606060',
    'lenco',
    'mtn',
    'pay-customer-a-001',
    253000,
    'success'
  ),
  (
    'f2f2f2f2-f2f2-f2f2-f2f2-f2f2f2f2f2f2',
    '90909090-9090-9090-9090-909090909090',
    'lenco',
    'airtel',
    'pay-customer-b-001',
    100000,
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
values
  (
    'd1d1d1d1-d1d1-d1d1-d1d1-d1d1d1d1d1d1',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    50000,
    'mtn',
    'po-vendor-a-001',
    'paid'
  ),
  (
    'd2d2d2d2-d2d2-d2d2-d2d2-d2d2d2d2d2d2',
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    75000,
    'mtn',
    'po-vendor-b-001',
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
  'a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1',
  '70707070-7070-7070-7070-707070707070',
  1,
  '{"item": 250000, "delivery": 0}'::jsonb,
  250000,
  'pending'
);

insert into public.invoices (
  id,
  series,
  no,
  order_id,
  snapshot
)
values (
  'b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1',
  'ZM',
  1,
  '70707070-7070-7070-7070-707070707070',
  '{"order_total_ngwee": 250000}'::jsonb
);

create or replace function pg_temp.set_auth(target_id uuid)
returns void
language plpgsql
as $$
begin
  perform set_config('request.jwt.claim.sub', target_id::text, true);
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

-- Zero-sum ledger trigger (force deferred check — outer test txn rolls back)
insert into public.ledger_transactions (id, kind)
values ('a3a3a3a3-a3a3-a3a3-a3a3-a3a3a3a3a3a3', 'payment_captured');
insert into public.ledger_postings (transaction_id, account_id, amount_ngwee)
values
  ('a3a3a3a3-a3a3-a3a3-a3a3-a3a3a3a3a3a3', 'e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1', 1000),
  ('a3a3a3a3-a3a3-a3a3-a3a3-a3a3a3a3a3a3', 'e2e2e2e2-e2e2-e2e2-e2e2-e2e2e2e2e2e2', -1000);

select extensions.lives_ok(
  $$set constraints ledger_postings_zero_sum immediate$$,
  'balanced ledger transaction passes zero-sum check'
);

select extensions.throws_ok(
  $unbal$
  do $inner$
  begin
    insert into public.ledger_transactions (id, kind)
    values ('a4a4a4a4-a4a4-a4a4-a4a4-a4a4a4a4a4a4', 'payment_captured');
    insert into public.ledger_postings (transaction_id, account_id, amount_ngwee)
    values
      ('a4a4a4a4-a4a4-a4a4-a4a4-a4a4a4a4a4a4', 'e1e1e1e1-e1e1-e1e1-e1e1-e1e1e1e1e1e1', 1000),
      ('a4a4a4a4-a4a4-a4a4-a4a4-a4a4a4a4a4a4', 'e2e2e2e2-e2e2-e2e2-e2e2-e2e2e2e2e2e2', -500);
    set constraints ledger_postings_zero_sum immediate;
  end
  $inner$;
  $unbal$,
  'P0001',
  null,
  'unbalanced ledger transaction rejected'
);

-- ---------------------------------------------------------------------------
-- Webhook + lenco_reference uniqueness / charset
-- ---------------------------------------------------------------------------

insert into public.webhook_events (provider, event_id, signature_valid, raw)
values ('lenco', 'evt-001', true, '{}'::jsonb);

select extensions.throws_ok(
  $$insert into public.webhook_events (provider, event_id, signature_valid, raw)
    values ('lenco', 'evt-001', true, '{}'::jsonb)$$,
  '23505',
  null,
  'duplicate webhook (provider, event_id) rejected'
);

select extensions.throws_ok(
  $$insert into public.payments (
      checkout_group_id, provider, rail, lenco_reference, amount_ngwee
    ) values (
      '60606060-6060-6060-6060-606060606060', 'lenco', 'mtn', 'pay-customer-a-001', 1
    )$$,
  '23505',
  null,
  'duplicate lenco_reference rejected'
);

select extensions.throws_ok(
  $$insert into public.payments (
      checkout_group_id, provider, rail, lenco_reference, amount_ngwee
    ) values (
      '60606060-6060-6060-6060-606060606060', 'lenco', 'mtn', 'pay bad charset!', 1
    )$$,
  '23514',
  null,
  'bad-charset lenco_reference rejected'
);

-- ---------------------------------------------------------------------------
-- Invoice counter concurrency (serialized via FOR UPDATE)
-- ---------------------------------------------------------------------------

select extensions.is(public.next_invoice_no('CONC'), 1::bigint, 'first invoice no is 1');
select extensions.is(public.next_invoice_no('CONC'), 2::bigint, 'second invoice no is 2');

do $$
declare
  n1 bigint;
  n2 bigint;
begin
  perform pg_advisory_xact_lock(66006);

  perform 1 from public.invoice_counters where series = 'CONC2' for update;
  if not found then
    insert into public.invoice_counters (series, next_no) values ('CONC2', 1);
  end if;

  begin
    perform set_config('vergeo.invoice_slot', '1', true);
    perform pg_sleep(0.05);
    perform set_config('vergeo.invoice_result_1', public.next_invoice_no('CONC2')::text, true);
  exception when others then
    perform set_config('vergeo.invoice_error_1', sqlerrm, true);
  end;

  select public.next_invoice_no('CONC2') into n2;
  perform set_config('vergeo.invoice_result_2', n2::text, true);
end;
$$;

select extensions.is(
  current_setting('vergeo.invoice_result_1'),
  '1',
  'concurrent slot 1 allocated invoice 1'
);
select extensions.is(
  current_setting('vergeo.invoice_result_2'),
  '2',
  'concurrent slot 2 allocated invoice 2 (serialized)'
);
select extensions.is(
  (select next_no from public.invoice_counters where series = 'CONC2'),
  3::bigint,
  'counter advanced to 3 after two allocations'
);

-- ---------------------------------------------------------------------------
-- RLS matrix (non-superuser)
-- ---------------------------------------------------------------------------

set session authorization vergeo_rls_tester;

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.is(
  (select count(*)::int from public.payments),
  1,
  'customer A reads own payment'
);
select extensions.is(
  (select count(*)::int from public.invoices),
  1,
  'customer A reads own invoice'
);
select extensions.is(
  (select count(*)::int from public.refunds),
  1,
  'customer A reads own refund'
);
select extensions.is(
  (select count(*)::int from public.payouts),
  0,
  'customer A cannot read payouts'
);
select extensions.is(
  (select count(*)::int from public.ledger_accounts),
  0,
  'customer A cannot read ledger_accounts'
);
select extensions.is(
  (select count(*)::int from public.webhook_events),
  0,
  'customer A cannot read webhook_events'
);

select pg_temp.set_auth('33333333-3333-3333-3333-333333333333');
select extensions.is(
  (select count(*)::int from public.payouts where vendor_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
  1,
  'vendor A reads own payout'
);
select extensions.is(
  (select count(*)::int from public.payouts where vendor_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'),
  0,
  'vendor A cannot read vendor B payout'
);
select extensions.is(
  (select count(*)::int from public.payments),
  0,
  'vendor A cannot read payments'
);

select pg_temp.set_auth('55555555-5555-5555-5555-555555555555');
select extensions.is(
  (select count(*)::int from public.payments),
  0,
  'stranger cannot read payments'
);
select extensions.is(
  (select count(*)::int from public.invoices),
  0,
  'stranger cannot read invoices'
);

select pg_temp.set_auth('11111111-1111-1111-1111-111111111111');
select extensions.throws_ok(
  $$insert into public.payments (
      checkout_group_id, provider, rail, lenco_reference, amount_ngwee
    ) values (
      '60606060-6060-6060-6060-606060606060', 'lenco', 'mtn', 'client-pay-attempt', 1
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
  'payments-by-checkout_group lookup uses checkout_group_id index'
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
    order by created_at desc
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
    where plan ilike '%payouts_vendor_id_created_at_idx%'
       or plan ilike '%Index Scan%payouts%vendor_id%'
  ),
  'payouts-by-vendor lookup uses vendor_id index'
);

select * from extensions.finish();
rollback;
