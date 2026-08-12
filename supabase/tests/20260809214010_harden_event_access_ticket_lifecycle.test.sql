-- Visibility and cancelled-ticket invariants (pgTAP via `supabase test db`).

begin;

set local search_path to public, extensions, auth;
select extensions.plan(21);

create or replace function pg_temp.seed_auth_user(target_id uuid, email text)
returns void
language plpgsql
as $$
begin
  insert into auth.users (
    instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
  )
  values (
    '00000000-0000-0000-0000-000000000000', target_id, 'authenticated',
    'authenticated', email, 'test-password-hash', timezone('utc', now()),
    '{}'::jsonb, '{}'::jsonb, timezone('utc', now()), timezone('utc', now())
  );
end;
$$;

select pg_temp.seed_auth_user(
  '91000000-0000-0000-0000-000000000001',
  'strategy-owner@test.local'
);
select pg_temp.seed_auth_user(
  '91000000-0000-0000-0000-000000000002',
  'strategy-stranger@test.local'
);
select pg_temp.seed_auth_user(
  '91000000-0000-0000-0000-000000000003',
  'strategy-holder@test.local'
);

-- The test connection owns auth.users; service_role intentionally does not.
-- Seed auth identities first, then exercise all application writes through the
-- same service role used by the API.
set local role service_role;

insert into public.profiles (id, phone, display_name)
values
  ('91000000-0000-0000-0000-000000000001', '+260971009101', 'Strategy Owner'),
  ('91000000-0000-0000-0000-000000000002', '+260971009102', 'Strategy Stranger'),
  ('91000000-0000-0000-0000-000000000003', '+260971009103', 'Strategy Holder')
on conflict (id) do update
  set phone = excluded.phone,
      display_name = excluded.display_name;

insert into public.user_roles (user_id, role)
values
  ('91000000-0000-0000-0000-000000000001', 'vendor'),
  ('91000000-0000-0000-0000-000000000002', 'customer'),
  ('91000000-0000-0000-0000-000000000003', 'customer')
on conflict (user_id, role) do nothing;

insert into public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier)
values (
  '91919191-9191-9191-9191-919191919191',
  '91000000-0000-0000-0000-000000000001',
  'strategy-events-vendor',
  'Strategy Events Vendor',
  'active',
  2
);

insert into public.events (
  id, organiser_vendor_id, title, slug, status, visibility, access_code_hash
)
values
  (
    '92000000-0000-0000-0000-000000000001',
    '91919191-9191-9191-9191-919191919191',
    'Listed Strategy Event', 'strategy-rls-public', 'published', 'public', null
  ),
  (
    '92000000-0000-0000-0000-000000000002',
    '91919191-9191-9191-9191-919191919191',
    'Unlisted Strategy Event', 'strategy-rls-unlisted', 'published', 'unlisted', null
  ),
  (
    '92000000-0000-0000-0000-000000000003',
    '91919191-9191-9191-9191-919191919191',
    'Private Strategy Event', 'strategy-rls-private', 'published', 'private',
    'private-code-digest'
  ),
  (
    '92000000-0000-0000-0000-000000000004',
    '91919191-9191-9191-9191-919191919191',
    'Cancellation Strategy Event', 'strategy-cancellation', 'published', 'public', null
  );

insert into public.event_instances (id, event_id, starts_at, ends_at, capacity)
values
  ('93000000-0000-0000-0000-000000000001', '92000000-0000-0000-0000-000000000001', timezone('utc', now()) + interval '7 days', timezone('utc', now()) + interval '7 days 2 hours', 20),
  ('93000000-0000-0000-0000-000000000002', '92000000-0000-0000-0000-000000000002', timezone('utc', now()) + interval '8 days', timezone('utc', now()) + interval '8 days 2 hours', 20),
  ('93000000-0000-0000-0000-000000000003', '92000000-0000-0000-0000-000000000003', timezone('utc', now()) + interval '9 days', timezone('utc', now()) + interval '9 days 2 hours', 20),
  ('93000000-0000-0000-0000-000000000004', '92000000-0000-0000-0000-000000000004', timezone('utc', now()) + interval '10 days', timezone('utc', now()) + interval '10 days 2 hours', 20);

insert into public.ticket_types (id, event_id, kind, name, price_ngwee)
values
  ('94000000-0000-0000-0000-000000000001', '92000000-0000-0000-0000-000000000001', 'fixed', 'Listed GA', 10000),
  ('94000000-0000-0000-0000-000000000002', '92000000-0000-0000-0000-000000000002', 'fixed', 'Unlisted GA', 10000),
  ('94000000-0000-0000-0000-000000000003', '92000000-0000-0000-0000-000000000003', 'fixed', 'Private GA', 10000),
  ('94000000-0000-0000-0000-000000000004', '92000000-0000-0000-0000-000000000004', 'fixed', 'Cancellation GA', 10000);

insert into public.ticket_type_instances (ticket_type_id, instance_id, allocation)
values
  ('94000000-0000-0000-0000-000000000001', '93000000-0000-0000-0000-000000000001', 20),
  ('94000000-0000-0000-0000-000000000002', '93000000-0000-0000-0000-000000000002', 20),
  ('94000000-0000-0000-0000-000000000003', '93000000-0000-0000-0000-000000000003', 20);

insert into public.ticket_type_price_tiers (ticket_type_id, min_qty, price_ngwee)
values
  ('94000000-0000-0000-0000-000000000001', 2, 9000),
  ('94000000-0000-0000-0000-000000000002', 2, 9000),
  ('94000000-0000-0000-0000-000000000003', 2, 9000);

insert into public.tickets (
  id, instance_id, ticket_type_id, holder_user_id, status, qr_secret
)
values
  ('95000000-0000-0000-0000-000000000001', '93000000-0000-0000-0000-000000000004', '94000000-0000-0000-0000-000000000004', '91000000-0000-0000-0000-000000000003', 'issued', 'cancel-me'),
  ('95000000-0000-0000-0000-000000000002', '93000000-0000-0000-0000-000000000004', '94000000-0000-0000-0000-000000000004', '91000000-0000-0000-0000-000000000003', 'checked_in', 'keep-audit');

insert into public.ticket_transfers (
  id, ticket_id, from_user_id, to_phone, status, expires_at
)
values (
  '96000000-0000-0000-0000-000000000001',
  '95000000-0000-0000-0000-000000000001',
  '91000000-0000-0000-0000-000000000003',
  '+260971009199',
  'pending',
  timezone('utc', now()) + interval '2 days'
);

create or replace function pg_temp.set_auth(target_id uuid)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    json_build_object('sub', target_id, 'role', 'authenticated')::text,
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
select pg_temp.set_anon();

select extensions.is(
  (select count(*)::int from public.events where id in (
    '92000000-0000-0000-0000-000000000001',
    '92000000-0000-0000-0000-000000000002',
    '92000000-0000-0000-0000-000000000003'
  )),
  1,
  'anon sees listed events only'
);
select extensions.is(
  (select count(*)::int from public.event_instances where event_id in (
    '92000000-0000-0000-0000-000000000001',
    '92000000-0000-0000-0000-000000000002',
    '92000000-0000-0000-0000-000000000003'
  )),
  1,
  'anon sees instances for listed events only'
);
select extensions.is(
  (select count(*)::int from public.ticket_types where id in (
    '94000000-0000-0000-0000-000000000001',
    '94000000-0000-0000-0000-000000000002',
    '94000000-0000-0000-0000-000000000003'
  )),
  1,
  'anon sees ticket types for listed events only'
);
select extensions.is(
  (select count(*)::int from public.ticket_type_instances where ticket_type_id in (
    '94000000-0000-0000-0000-000000000001',
    '94000000-0000-0000-0000-000000000002',
    '94000000-0000-0000-0000-000000000003'
  )),
  1,
  'anon sees allocations for listed events only'
);
select extensions.is(
  (select count(*)::int from public.ticket_type_price_tiers where ticket_type_id in (
    '94000000-0000-0000-0000-000000000001',
    '94000000-0000-0000-0000-000000000002',
    '94000000-0000-0000-0000-000000000003'
  )),
  1,
  'anon sees price tiers for listed events only'
);
select extensions.is(
  (select count(*)::int from public.events where access_code_hash is not null),
  0,
  'anon cannot read a private event access-code digest'
);

reset role;
select pg_temp.set_auth('91000000-0000-0000-0000-000000000002');
select extensions.is(
  (select count(*)::int from public.events where id in (
    '92000000-0000-0000-0000-000000000001',
    '92000000-0000-0000-0000-000000000002',
    '92000000-0000-0000-0000-000000000003'
  )),
  1,
  'unrelated authenticated users see listed events only'
);

reset role;
select pg_temp.set_auth('91000000-0000-0000-0000-000000000001');
select extensions.is(
  (select count(*)::int from public.events where id in (
    '92000000-0000-0000-0000-000000000001',
    '92000000-0000-0000-0000-000000000002',
    '92000000-0000-0000-0000-000000000003'
  )),
  3,
  'the organiser can still read their non-public events'
);
select extensions.is(
  (select access_code_hash from public.events where id = '92000000-0000-0000-0000-000000000003'),
  'private-code-digest',
  'the organiser can read the stored private-event digest'
);

reset role;
set local role service_role;
select extensions.throws_ok(
  $$insert into public.events (
      organiser_vendor_id, title, slug, status, visibility, access_code_hash
    ) values (
      '91919191-9191-9191-9191-919191919191', 'Bad Hash',
      'strategy-bad-public-hash', 'published', 'public', 'must-not-persist'
    )$$,
  '23514'
);
select extensions.throws_ok(
  $$update public.events
    set visibility = 'public'
    where id = '92000000-0000-0000-0000-000000000003'$$,
  '23514'
);

insert into public.event_instances (id, event_id, starts_at, capacity)
values (
  '93000000-0000-0000-0000-000000000005',
  '92000000-0000-0000-0000-000000000001',
  '2026-09-01 10:00:00+00'::timestamptz,
  5
);
select extensions.is(
  (select ends_at from public.event_instances where id = '93000000-0000-0000-0000-000000000005'),
  '2026-09-01 12:00:00+00'::timestamptz,
  'legacy instance inserts receive an explicit two-hour end'
);
update public.event_instances
set starts_at = '2026-09-01 11:00:00+00'::timestamptz
where id = '93000000-0000-0000-0000-000000000005';
select extensions.is(
  (select ends_at - starts_at from public.event_instances where id = '93000000-0000-0000-0000-000000000005'),
  interval '2 hours',
  'start-only reschedules preserve the previous duration'
);
select extensions.throws_ok(
  $$update public.event_instances
    set ends_at = starts_at
    where id = '93000000-0000-0000-0000-000000000005'$$,
  '23514'
);

update public.events
set status = 'cancelled'
where id = '92000000-0000-0000-0000-000000000004';

select extensions.is(
  (select status from public.tickets where id = '95000000-0000-0000-0000-000000000001'),
  'void',
  'cancelling an event voids active ticket credentials'
);
select extensions.is(
  (select status from public.tickets where id = '95000000-0000-0000-0000-000000000002'),
  'checked_in',
  'cancellation preserves checked-in ticket audit rows'
);
select extensions.is(
  (select status from public.ticket_transfers where id = '96000000-0000-0000-0000-000000000001'),
  'cancelled',
  'cancellation cancels pending ticket transfers'
);
select extensions.ok(
  (select cancelled_at is not null from public.ticket_transfers where id = '96000000-0000-0000-0000-000000000001'),
  'cancelled transfers record their cancellation time'
);
select extensions.throws_ok(
  $$insert into public.tickets (
      instance_id, ticket_type_id, holder_user_id, status
    ) values (
      '93000000-0000-0000-0000-000000000004',
      '94000000-0000-0000-0000-000000000004',
      '91000000-0000-0000-0000-000000000003',
      'issued'
    )$$,
  '23514'
);
select extensions.is(
  has_function_privilege(
    'authenticated',
    'public.require_published_event_for_issued_ticket()',
    'execute'
  ),
  false,
  'clients cannot execute the issued-ticket guard directly'
);
select extensions.is(
  has_function_privilege(
    'authenticated',
    'public.cancel_active_tickets_for_event()',
    'execute'
  ),
  false,
  'clients cannot execute the cancellation trigger function directly'
);

select * from extensions.finish();
rollback;
