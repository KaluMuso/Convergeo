-- Fix bump_rate_counter's service-role check against the current hosted
-- Supabase/PostgREST claim contract.
--
-- Staging run #55's aftermath proved GET /discovery/home returning HTTP 500,
-- traced to POST /rest/v1/rpc/bump_rate_counter returning HTTP 400
-- "bump_rate_counter requires service role" for a call authenticated with a
-- genuine service-role key against the current staging project
-- (iyasmrmbcrvlfxpzescb) — confirmed the service-role credential itself is
-- valid, so the rejection is in this function's own authorization check.
--
-- That check read the JWT role claim via the legacy flattened GUC
-- `current_setting('request.jwt.claim.role', true)`. The current hosted
-- platform contract exposes claims as the JSON blob under
-- `request.jwt.claims`, which Supabase's own `auth.role()` helper reads
-- (provided by every Supabase project's `auth` schema — not something this
-- repo defines). A hosted project that no longer populates the legacy
-- flattened per-claim GUC makes the old check reject every caller,
-- including a genuine service_role request, exactly matching the observed
-- failure.
--
-- Fix: switch the JWT-role comparison to `auth.role()`. The trusted direct
-- DB session bypass (`session_user in ('postgres', 'supabase_admin')`,
-- matching the guard-function convention in 0057/0058) is unchanged; anon
-- and authenticated remain rejected (auth.role() returns 'anon' /
-- 'authenticated' for them, never 'service_role'). No other behavior
-- changes: invalid-scope/limit/window validation and the counter
-- increment/window logic are byte-for-byte unchanged from
-- 20260813160000_rate_counter_scope_manifest.sql.
create or replace function public.bump_rate_counter(
  p_scope text,
  p_key text,
  p_window interval,
  p_limit integer
)
returns table (allowed boolean, retry_after_seconds integer)
language plpgsql
security definer
set search_path = public, private, extensions
as $$
declare
  v_window_start timestamptz;
  v_expires_at timestamptz;
  v_count integer;
  v_existing_count integer;
  v_existing_expires timestamptz;
  v_window_seconds double precision;
begin
  if not exists (
    select 1 from private.rate_counter_scope_manifest where scope = p_scope
  ) then
    raise exception 'invalid rate counter scope: %', p_scope;
  end if;

  if p_limit <= 0 then
    raise exception 'p_limit must be positive';
  end if;

  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(auth.role(), '') is distinct from 'service_role' then
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
  'Sliding-window rate counter increment. Callable by service_role (checked via '
  'auth.role(), the current hosted PostgREST/GoTrue claim contract) or a trusted '
  'direct DB session (postgres/supabase_admin). anon/authenticated are rejected.';

revoke all on function public.bump_rate_counter(text, text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.bump_rate_counter(text, text, interval, integer)
  to service_role;
