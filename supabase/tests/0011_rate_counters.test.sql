-- M04-P07 rate_counters — migration apply, bump atomicity, RLS, TTL cleanup
-- Requires: 0001_extensions.sql through 0011_rate_counters.sql
-- Run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0011_rate_counters.test.sql

\set ON_ERROR_STOP on

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
-- bump_rate_counter: allow until limit, then deny with retry_after
-- ---------------------------------------------------------------------------
do $$
declare
  v_allowed boolean;
  v_retry integer;
  v_i integer;
  v_test_key text := 'test-number-' || gen_random_uuid()::text;
begin
  delete from public.rate_counters where key = v_test_key;

  for v_i in 1..5 loop
    select allowed, retry_after_seconds
    into v_allowed, v_retry
    from public.bump_rate_counter('otp_number', v_test_key, interval '1 hour', 5);

    if not v_allowed then
      raise exception 'expected allow on attempt %, got deny (retry=%)', v_i, v_retry;
    end if;
  end loop;

  select allowed, retry_after_seconds
  into v_allowed, v_retry
  from public.bump_rate_counter('otp_number', v_test_key, interval '1 hour', 5);

  if v_allowed then
    raise exception 'expected deny after limit reached';
  end if;

  if v_retry < 1 then
    raise exception 'expected positive retry_after on deny, got %', v_retry;
  end if;

  delete from public.rate_counters where key = v_test_key;
end;
$$;

-- ---------------------------------------------------------------------------
-- per-number vs per-IP independence
-- ---------------------------------------------------------------------------
do $$
declare
  v_allowed boolean;
  v_number_key text := 'number-' || gen_random_uuid()::text;
  v_ip_key text := 'ip-' || gen_random_uuid()::text;
begin
  delete from public.rate_counters where key in (v_number_key, v_ip_key);

  select allowed into v_allowed
  from public.bump_rate_counter('otp_number', v_number_key, interval '1 hour', 1);
  if not v_allowed then
    raise exception 'number scope should allow first bump';
  end if;

  select allowed into v_allowed
  from public.bump_rate_counter('otp_number', v_number_key, interval '1 hour', 1);
  if v_allowed then
    raise exception 'number scope should deny second bump in same window';
  end if;

  select allowed into v_allowed
  from public.bump_rate_counter('otp_ip', v_ip_key, interval '1 day', 1);
  if not v_allowed then
    raise exception 'ip scope should remain independent and allow first bump';
  end if;

  delete from public.rate_counters where key in (v_number_key, v_ip_key);
end;
$$;

-- ---------------------------------------------------------------------------
-- TTL cleanup removes expired rows
-- ---------------------------------------------------------------------------
do $$
declare
  v_deleted bigint;
  v_key text := 'ttl-' || gen_random_uuid()::text;
begin
  insert into public.rate_counters (scope, key, window_start, count, expires_at)
  values ('auth_ip', v_key, now() - interval '2 hours', 1, now() - interval '1 hour');

  v_deleted := public.cleanup_expired_rate_counters();
  if v_deleted < 1 then
    raise exception 'cleanup_expired_rate_counters should delete at least one row, got %', v_deleted;
  end if;

  if exists (select 1 from public.rate_counters where key = v_key) then
    raise exception 'expired row was not deleted';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS: authenticated client cannot read rate_counters
-- ---------------------------------------------------------------------------
do $$
declare
  v_count integer;
begin
  set local role vergeo_rls_tester;
  perform set_config('request.jwt.claim.role', 'authenticated', true);
  perform set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);

  select count(*) into v_count from public.rate_counters;
  if v_count <> 0 then
    raise exception 'authenticated client should not read rate_counters, saw % rows', v_count;
  end if;

  reset role;
end;
$$;

do $$
begin
  raise notice '0011_rate_counters tests passed';
end;
$$;
