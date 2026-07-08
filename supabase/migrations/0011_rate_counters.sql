-- M04-P07: Postgres-backed rate counters for OTP/auth abuse guards (no Redis).

-- ---------------------------------------------------------------------------
-- rate_counters (service-role only — clients never read/write)
-- ---------------------------------------------------------------------------
create table public.rate_counters (
  id uuid primary key default gen_random_uuid(),
  scope text not null check (scope in ('otp_number', 'otp_ip', 'auth_ip', 'auth_number')),
  key text not null,
  window_start timestamptz not null,
  count integer not null default 0 check (count >= 0),
  expires_at timestamptz not null,
  unique (scope, key, window_start)
);

create index rate_counters_expires_at_idx
  on public.rate_counters (expires_at);

create index rate_counters_scope_key_idx
  on public.rate_counters (scope, key);

comment on table public.rate_counters is
  'OTP/auth rate-limit counters; RLS enabled with zero client policies — service_role only.';

-- ---------------------------------------------------------------------------
-- session_user guard — block direct client mutations (security definer RPC only)
-- ---------------------------------------------------------------------------
create or replace function public.guard_rate_counters_mutation()
returns trigger
language plpgsql
as $$
begin
  if session_user in ('postgres', 'supabase_admin') then
    return coalesce(new, old);
  end if;

  if coalesce(current_setting('request.jwt.claim.role', true), '') = 'service_role' then
    return coalesce(new, old);
  end if;

  raise exception 'rate_counters is service-role only';
end;
$$;

create trigger rate_counters_guard_mutation
  before insert or update or delete on public.rate_counters
  for each row
  execute function public.guard_rate_counters_mutation();

-- ---------------------------------------------------------------------------
-- Atomic counter bump (security definer — bypasses RLS for service paths)
-- ---------------------------------------------------------------------------
create or replace function public.bump_rate_counter(
  p_scope text,
  p_key text,
  p_window interval,
  p_limit integer
)
returns table (allowed boolean, retry_after_seconds integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_window_start timestamptz;
  v_expires_at timestamptz;
  v_count integer;
  v_existing_count integer;
  v_existing_expires timestamptz;
  v_window_seconds double precision;
begin
  if p_scope not in ('otp_number', 'otp_ip', 'auth_ip', 'auth_number') then
    raise exception 'invalid rate counter scope: %', p_scope;
  end if;

  if p_limit <= 0 then
    raise exception 'p_limit must be positive';
  end if;

  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'bump_rate_counter requires service role';
  end if;

  v_window_seconds := extract(epoch from p_window);
  if v_window_seconds <= 0 then
    raise exception 'p_window must be positive';
  end if;

  v_window_start := to_timestamp(
    floor(extract(epoch from now()) / v_window_seconds) * v_window_seconds
  );
  v_expires_at := v_window_start + p_window;

  insert into public.rate_counters as rc (scope, key, window_start, count, expires_at)
  values (p_scope, p_key, v_window_start, 1, v_expires_at)
  on conflict (scope, key, window_start)
  do update
    set count = rc.count + 1
  where rc.count < p_limit
  returning rc.count, rc.expires_at
  into v_count, v_expires_at;

  if found then
    allowed := true;
    retry_after_seconds := greatest(
      0,
      ceil(extract(epoch from (v_expires_at - now())))::integer
    );
    return next;
    return;
  end if;

  select rc.count, rc.expires_at
  into v_existing_count, v_existing_expires
  from public.rate_counters rc
  where rc.scope = p_scope
    and rc.key = p_key
    and rc.window_start = v_window_start
  for update;

  if v_existing_count is null then
  -- Lost race: row did not exist on conflict path; retry insert once.
    insert into public.rate_counters (scope, key, window_start, count, expires_at)
    values (p_scope, p_key, v_window_start, 1, v_expires_at)
    on conflict (scope, key, window_start) do nothing;

    select rc.count, rc.expires_at
    into v_existing_count, v_existing_expires
    from public.rate_counters rc
    where rc.scope = p_scope
      and rc.key = p_key
      and rc.window_start = v_window_start
    for update;
  end if;

  if v_existing_count < p_limit then
    update public.rate_counters rc
    set count = rc.count + 1
    where rc.scope = p_scope
      and rc.key = p_key
      and rc.window_start = v_window_start
      and rc.count < p_limit
    returning rc.count, rc.expires_at
    into v_count, v_expires_at;

    if found then
      allowed := true;
      retry_after_seconds := greatest(
        0,
        ceil(extract(epoch from (v_expires_at - now())))::integer
      );
      return next;
      return;
    end if;
  end if;

  allowed := false;
  retry_after_seconds := greatest(
    1,
    ceil(extract(epoch from (v_existing_expires - now())))::integer
  );
  return next;
end;
$$;

comment on function public.bump_rate_counter(text, text, interval, integer) is
  'Atomically upserts the current fixed window counter and returns allow/deny + retry-after seconds.';

-- ---------------------------------------------------------------------------
-- TTL cleanup helper
-- ---------------------------------------------------------------------------
create or replace function public.cleanup_expired_rate_counters()
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  v_deleted bigint;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'cleanup_expired_rate_counters requires service role';
  end if;

  delete from public.rate_counters
  where expires_at < now();

  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

comment on function public.cleanup_expired_rate_counters() is
  'Deletes expired rate counter rows; intended for scheduled n8n/cron cleanup.';

-- ---------------------------------------------------------------------------
-- Tunable OTP/auth limits (platform_config)
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  (
    'otp_cap_per_number_hour',
    '5'::jsonb,
    'Maximum OTP send attempts per phone number per hour'
  ),
  (
    'otp_cap_per_ip_day',
    '20'::jsonb,
    'Maximum OTP send attempts per client IP per day'
  ),
  (
    'otp_resend_cooldown_base_seconds',
    '30'::jsonb,
    'Base OTP resend cooldown in seconds (exponential backoff seed)'
  ),
  (
    'otp_resend_cooldown_max_seconds',
    '900'::jsonb,
    'Maximum OTP resend cooldown cap in seconds (15 minutes)'
  ),
  (
    'auth_endpoint_cap_per_ip_minute',
    '60'::jsonb,
    'Global auth-guard endpoint requests per IP per minute'
  )
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Row level security (zero client policies — service_role only)
-- ---------------------------------------------------------------------------
alter table public.rate_counters enable row level security;
alter table public.rate_counters force row level security;

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on table public.rate_counters to service_role;
grant execute on function public.bump_rate_counter(text, text, interval, integer) to service_role;
grant execute on function public.cleanup_expired_rate_counters() to service_role;
