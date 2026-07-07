-- M03-P07 config tables — seed assertions, RLS smoke, audit trail
-- Requires: 0001_extensions.sql, 0002_identity_vendors.sql (has_role + user_roles), 0008_config.sql
-- Run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0008_config.test.sql
--   or via supabase test db when pgTAP harness is wired (M03-P09)

\set ON_ERROR_STOP on

-- Non-superuser for RLS tests (postgres bypasses RLS even with FORCE)
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'vergeo_rls_tester') then
    create role vergeo_rls_tester login password 'test' nosuperuser nobypassrls;
    grant authenticated to vergeo_rls_tester;
    grant anon to vergeo_rls_tester;
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- Test fixtures (service-role / superuser context)
-- ---------------------------------------------------------------------------
do $$
declare
  v_customer_id uuid := '11111111-1111-1111-1111-111111111111';
  v_admin_id uuid := '22222222-2222-2222-2222-222222222222';
begin
  if to_regprocedure('public.has_role(text)') is null then
    raise exception 'missing public.has_role(text) — apply 0002_identity_vendors.sql first';
  end if;

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
  ) values
    (
      '00000000-0000-0000-0000-000000000000',
      v_customer_id,
      'authenticated',
      'authenticated',
      'customer-config-test@vergeo5.local',
      crypt('test-password', gen_salt('bf')),
      now(),
      '{}'::jsonb,
      '{}'::jsonb,
      now(),
      now()
    ),
    (
      '00000000-0000-0000-0000-000000000000',
      v_admin_id,
      'authenticated',
      'authenticated',
      'admin-config-test@vergeo5.local',
      crypt('test-password', gen_salt('bf')),
      now(),
      '{}'::jsonb,
      '{}'::jsonb,
      now(),
      now()
    )
  on conflict (id) do nothing;

  insert into public.user_roles (user_id, role)
  values (v_admin_id, 'admin')
  on conflict do nothing;
end;
$$;

-- ---------------------------------------------------------------------------
-- Seed-value assertions (D4 / D12 / D16 / D23)
-- ---------------------------------------------------------------------------
do $$
declare
  v_count integer;
  v_value jsonb;
begin
  select count(*) into v_count
  from public.commission_rates
  where (category_key, rate_bps) in (
    ('electronics', 500),
    ('home', 800),
    ('fashion_beauty', 1000),
    ('services', 1200),
    ('event_tickets', 500),
    ('supplies', 300),
    ('groceries', 500),
    ('default', 800),
    ('free_events', 0)
  );
  if v_count <> 9 then
    raise exception 'commission_rates seed mismatch: expected 9 D4 rows, got %', v_count;
  end if;

  select value into v_value from public.platform_config where key = 'cod_cap_ngwee';
  if (v_value)::text::bigint <> 50000 then
    raise exception 'cod_cap_ngwee expected 50000 ngwee, got %', v_value;
  end if;

  select value into v_value from public.platform_config where key = 'free_delivery_threshold_ngwee';
  if (v_value)::text::bigint <> 20000 then
    raise exception 'free_delivery_threshold_ngwee expected 20000 ngwee, got %', v_value;
  end if;

  select value into v_value from public.platform_config where key = 'ai_guest_quota';
  if (v_value)::text::integer <> 3 then
    raise exception 'ai_guest_quota expected 3, got %', v_value;
  end if;

  select value into v_value from public.platform_config where key = 'ai_free_monthly_quota';
  if (v_value)::text::integer <> 25 then
    raise exception 'ai_free_monthly_quota expected 25, got %', v_value;
  end if;

  select value into v_value from public.platform_config where key = 'ai_monthly_cap_usd';
  if (v_value)::text::integer <> 15 then
    raise exception 'ai_monthly_cap_usd expected 15, got %', v_value;
  end if;

  select count(*) into v_count
  from public.feature_flags
  where enabled = true;
  if v_count <> 0 then
    raise exception 'feature_flags: expected all OFF at launch, found % enabled', v_count;
  end if;

  select count(*) into v_count from public.prohibited_categories;
  if v_count <> 7 then
    raise exception 'prohibited_categories expected 7 rows, got %', v_count;
  end if;
end;
$$;

do $$
declare
  v_max_listings integer;
  v_cap bigint;
  v_count integer;
begin
  select max_listings, first_orders_cap_ngwee, first_orders_count
  into v_max_listings, v_cap, v_count
  from public.vendor_quotas
  where tier = 1;

  if v_max_listings <> 30 or v_cap <> 50000 or v_count <> 5 then
    raise exception 'vendor_quotas tier 1 mismatch: listings=%, cap=%, count=%',
      v_max_listings, v_cap, v_count;
  end if;

  if exists (
    select 1 from public.vendor_quotas
    where tier in (2, 3)
      and (first_orders_cap_ngwee is not null or first_orders_count is not null)
  ) then
    raise exception 'vendor_quotas tiers 2/3 should have null first-order caps';
  end if;
end;
$$;

\echo 'PASS: seed-value assertions'

set session authorization vergeo_rls_tester;

-- ---------------------------------------------------------------------------
-- RLS: anon can read commission_rates
-- ---------------------------------------------------------------------------
begin;
set local role anon;
select count(*) as anon_commission_rates_visible
from public.commission_rates;

do $$
declare
  v_count integer;
begin
  select count(*) into v_count from public.commission_rates;
  if v_count < 1 then
    raise exception 'anon should read commission_rates';
  end if;
end;
$$;

commit;
\echo 'PASS: anon read commission_rates'

-- ---------------------------------------------------------------------------
-- RLS: authed non-admin cannot update config tables
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

do $$
declare
  v_rows integer;
  v_rate integer;
begin
  update public.commission_rates set rate_bps = 999 where category_key = 'default';
  get diagnostics v_rows = row_count;
  select rate_bps into v_rate from public.commission_rates where category_key = 'default';

  if v_rows <> 0 or v_rate = 999 then
    raise exception 'non-admin update should be denied (rows=%, rate=%)', v_rows, v_rate;
  end if;
end;
$$;

commit;
\echo 'PASS: non-admin write denied on commission_rates'

-- ---------------------------------------------------------------------------
-- RLS: admin can update; audit row written with before/after
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

do $$
declare
  v_before integer;
  v_after integer;
  v_audit_count integer;
begin
  select rate_bps into v_before from public.commission_rates where category_key = 'electronics';

  update public.commission_rates
  set rate_bps = v_before + 1
  where category_key = 'electronics';

  select rate_bps into v_after from public.commission_rates where category_key = 'electronics';

  if v_after <> v_before + 1 then
    raise exception 'admin update failed: before % after %', v_before, v_after;
  end if;

  select count(*) into v_audit_count
  from public.config_audit
  where table_name = 'commission_rates'
    and row_key = 'electronics'
    and before is not null
    and after is not null
    and (before ->> 'rate_bps')::integer = v_before
    and (after ->> 'rate_bps')::integer = v_after;

  if v_audit_count < 1 then
    raise exception 'config_audit missing before/after for admin commission_rates update';
  end if;

  -- restore seed value
  update public.commission_rates
  set rate_bps = v_before
  where category_key = 'electronics';
end;
$$;

commit;
\echo 'PASS: admin update + config_audit before/after'

reset session authorization;

\echo 'ALL 0008_config tests passed'
