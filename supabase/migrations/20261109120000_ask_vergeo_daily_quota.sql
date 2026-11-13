-- Ask Vergeo upgrade: daily (Alibaba-style) quotas, premium tier flag, reservation release.
--
-- Additive only. The M06-P03 monthly RPC (reserve_ask_quota) is left in place for
-- rollback; the API now calls reserve_ask_quota_daily. The $15/mo global kill-switch
-- (ask_spend_monthly + finalize_ask_answer) is unchanged.
--
-- Limits live in platform_config (admin-editable):
--   ai_guest_daily_quota   (default 3)   — guests, keyed by device key OR client IP
--   ai_free_daily_quota    (default 10)  — signed-in free accounts
--   ai_premium_daily_quota (default 100) — users flagged premium in ask_user_tiers
-- Days roll over at midnight Africa/Lusaka.
--
-- Reversible rollback:
--   DROP FUNCTION IF EXISTS public.release_ask_reservation(uuid);
--   DROP FUNCTION IF EXISTS public.ask_quota_status(uuid, text, inet);
--   DROP FUNCTION IF EXISTS public.reserve_ask_quota_daily(uuid, text, inet, text);
--   DROP FUNCTION IF EXISTS public.ask_daily_used(uuid, text, inet, date);
--   DROP FUNCTION IF EXISTS public.ask_daily_limit_for_tier(text);
--   DROP FUNCTION IF EXISTS public.ask_resolve_tier(uuid);
--   DROP FUNCTION IF EXISTS public.ask_current_day_key();
--   DROP TABLE IF EXISTS public.ask_user_tiers;
--   DROP INDEX IF EXISTS public.ask_usage_user_day_idx;
--   DROP INDEX IF EXISTS public.ask_usage_guest_day_idx;
--   DROP INDEX IF EXISTS public.ask_usage_ip_day_idx;
--   ALTER TABLE public.ask_usage DROP COLUMN IF EXISTS day_key;
--   DELETE FROM public.platform_config
--     WHERE key IN ('ai_guest_daily_quota', 'ai_free_daily_quota', 'ai_premium_daily_quota');
--   UPDATE public.platform_config
--     SET value = value - 'moonshotai/kimi-k2' - 'google/gemini-2.0-flash-001'
--                       - 'google/gemini-2.0-flash-lite-001'
--     WHERE key = 'ai_model_rates';

-- ---------------------------------------------------------------------------
-- Day key on ask_usage (Africa/Lusaka calendar day)
-- ---------------------------------------------------------------------------
create or replace function public.ask_current_day_key()
returns date
language sql
stable
set search_path = public
as $$
  select (timezone('Africa/Lusaka', now()))::date;
$$;

alter table public.ask_usage add column if not exists day_key date;

-- Backfill existing rows from created_at (runs as migration owner; the
-- guard_ask_usage_mutation trigger permits postgres/supabase_admin).
update public.ask_usage
set day_key = (timezone('Africa/Lusaka', created_at))::date
where day_key is null;

alter table public.ask_usage
  alter column day_key set default (timezone('Africa/Lusaka', now()))::date;

alter table public.ask_usage alter column day_key set not null;

create index if not exists ask_usage_user_day_idx
  on public.ask_usage (user_id, day_key)
  where user_id is not null;

create index if not exists ask_usage_guest_day_idx
  on public.ask_usage (guest_key, day_key)
  where guest_key is not null;

create index if not exists ask_usage_ip_day_idx
  on public.ask_usage (client_ip, day_key)
  where client_ip is not null;

comment on column public.ask_usage.day_key is
  'Africa/Lusaka calendar day the question was reserved; daily quota window.';

-- ---------------------------------------------------------------------------
-- ask_user_tiers — premium flag (no payment yet; admin/service grants it)
-- ---------------------------------------------------------------------------
create table if not exists public.ask_user_tiers (
  user_id uuid primary key references auth.users (id) on delete cascade,
  tier text not null default 'free' check (tier in ('free', 'premium')),
  expires_at timestamptz,
  note text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger ask_user_tiers_set_updated_at
  before update on public.ask_user_tiers
  for each row
  execute function public.set_updated_at();

comment on table public.ask_user_tiers is
  'Ask Vergeo tier flag per user (free|premium). Service-role writes only; no billing yet.';

alter table public.ask_user_tiers enable row level security;
alter table public.ask_user_tiers force row level security;

-- Users may read their own tier row; admins may read all. No client write policies:
-- grants/revokes go through the service role (admin API) only.
create policy ask_user_tiers_select_own_or_admin
  on public.ask_user_tiers
  for select
  to authenticated
  using (user_id = (select auth.uid()) or public.has_role('admin'));

revoke all on public.ask_user_tiers from anon, authenticated;
grant select on public.ask_user_tiers to authenticated;

-- ---------------------------------------------------------------------------
-- Config seeds
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description)
values
  ('ai_guest_daily_quota', '3'::jsonb, 'Ask Vergeo guest questions per Lusaka day'),
  ('ai_free_daily_quota', '10'::jsonb, 'Ask Vergeo signed-in free questions per Lusaka day'),
  ('ai_premium_daily_quota', '100'::jsonb, 'Ask Vergeo premium-tier questions per Lusaka day')
on conflict (key) do nothing;

-- Kimi K2 blended rate (input ~$0.6/M, output ~$2.5/M, prompts are input-heavy):
-- 1.00 USD per 1M tokens is a deliberately conservative blend so the $15 kill-switch
-- trips early rather than late. Existing keys are preserved (jsonb concat).
update public.platform_config
set value = jsonb_build_object(
    'moonshotai/kimi-k2', 1.0,
    'google/gemini-2.0-flash-001', 0.15,
    'google/gemini-2.0-flash-lite-001', 0.1
  ) || value
where key = 'ai_model_rates'
  and jsonb_typeof(value) = 'object';

-- ---------------------------------------------------------------------------
-- Tier + limit helpers
-- ---------------------------------------------------------------------------
create or replace function public.ask_resolve_tier(p_user_id uuid)
returns text
language sql
stable
security definer
set search_path = public
as $$
  select case
    when p_user_id is null then 'guest'
    when exists (
      select 1
      from public.ask_user_tiers t
      where t.user_id = p_user_id
        and t.tier = 'premium'
        and (t.expires_at is null or t.expires_at > now())
    ) then 'premium'
    else 'free'
  end;
$$;

create or replace function public.ask_daily_limit_for_tier(p_tier text)
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select case p_tier
    when 'guest' then public.ask_read_config_int('ai_guest_daily_quota', 3)
    when 'premium' then public.ask_read_config_int('ai_premium_daily_quota', 100)
    else public.ask_read_config_int('ai_free_daily_quota', 10)
  end;
$$;

create or replace function public.ask_daily_used(
  p_user_id uuid,
  p_guest_key text,
  p_client_ip inet,
  p_day_key date
)
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select case
    when p_user_id is not null then (
      select count(*)::integer
      from public.ask_usage au
      where au.user_id = p_user_id
        and au.day_key = p_day_key
        and au.status in ('reserved', 'answered')
    )
    else (
      select count(*)::integer
      from public.ask_usage au
      where au.user_id is null
        and au.day_key = p_day_key
        and au.status in ('reserved', 'answered')
        and (
          (nullif(trim(p_guest_key), '') is not null and au.guest_key = trim(p_guest_key))
          or (p_client_ip is not null and au.client_ip = p_client_ip)
        )
    )
  end;
$$;

-- ---------------------------------------------------------------------------
-- Read-only quota status (GET /ask/quota)
-- ---------------------------------------------------------------------------
create or replace function public.ask_quota_status(
  p_user_id uuid,
  p_guest_key text,
  p_client_ip inet
)
returns table (tier text, daily_limit integer, used integer, remaining integer)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_tier text;
  v_limit integer;
  v_used integer;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'ask_quota_status requires service role';
  end if;

  v_tier := public.ask_resolve_tier(p_user_id);
  v_limit := public.ask_daily_limit_for_tier(v_tier);
  v_used := public.ask_daily_used(p_user_id, p_guest_key, p_client_ip, public.ask_current_day_key());

  tier := v_tier;
  daily_limit := v_limit;
  used := v_used;
  remaining := greatest(v_limit - v_used, 0);
  return next;
end;
$$;

-- ---------------------------------------------------------------------------
-- Atomic daily reservation
-- ---------------------------------------------------------------------------
create or replace function public.reserve_ask_quota_daily(
  p_user_id uuid,
  p_guest_key text,
  p_client_ip inet,
  p_question_hash text
)
returns table (
  reservation_id uuid,
  allowed boolean,
  reason text,
  tier text,
  daily_limit integer,
  used integer,
  remaining integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_day date;
  v_tier text;
  v_limit integer;
  v_used integer;
  v_guest_key text;
  v_reservation_id uuid;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'reserve_ask_quota_daily requires service role';
  end if;

  v_guest_key := nullif(trim(p_guest_key), '');
  if p_user_id is null and v_guest_key is null and p_client_ip is null then
    raise exception 'reserve_ask_quota_daily needs a user, guest key or client ip';
  end if;

  -- Serialize concurrent reservations for the same principal (race-safe count+insert).
  if p_user_id is not null then
    perform pg_advisory_xact_lock(hashtextextended('ask_quota:u:' || p_user_id::text, 0));
  else
    if p_client_ip is not null then
      perform pg_advisory_xact_lock(hashtextextended('ask_quota:ip:' || host(p_client_ip), 0));
    end if;
    if v_guest_key is not null then
      perform pg_advisory_xact_lock(hashtextextended('ask_quota:g:' || v_guest_key, 0));
    end if;
  end if;

  v_day := public.ask_current_day_key();
  v_tier := public.ask_resolve_tier(p_user_id);
  v_limit := public.ask_daily_limit_for_tier(v_tier);
  v_used := public.ask_daily_used(p_user_id, v_guest_key, p_client_ip, v_day);

  tier := v_tier;
  daily_limit := v_limit;

  if v_used >= v_limit then
    reservation_id := null;
    allowed := false;
    reason := case when v_tier = 'guest' then 'guest_exceeded' else 'daily_exceeded' end;
    used := v_used;
    remaining := 0;
    return next;
    return;
  end if;

  insert into public.ask_usage (
    user_id, guest_key, client_ip, question_hash, month_key, day_key, status
  )
  values (
    p_user_id,
    v_guest_key,
    p_client_ip,
    nullif(trim(p_question_hash), ''),
    public.ask_current_month_key(),
    v_day,
    'reserved'
  )
  returning id into v_reservation_id;

  reservation_id := v_reservation_id;
  allowed := true;
  reason := 'ok';
  used := v_used + 1;
  remaining := greatest(v_limit - v_used - 1, 0);
  return next;
end;
$$;

comment on function public.reserve_ask_quota_daily(uuid, text, inet, text) is
  'Atomically reserves one Ask slot against the tier''s daily limit (Africa/Lusaka day).';

-- ---------------------------------------------------------------------------
-- Release an unanswered reservation (provider error / fallback) — refunds the slot
-- ---------------------------------------------------------------------------
create or replace function public.release_ask_reservation(p_reservation_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'release_ask_reservation requires service role';
  end if;

  delete from public.ask_usage au
  where au.id = p_reservation_id
    and au.status = 'reserved';

  return found;
end;
$$;

comment on function public.release_ask_reservation(uuid) is
  'Deletes a still-reserved Ask row so a provider failure does not burn the user''s quota.';

-- ---------------------------------------------------------------------------
-- Execute grants — service role only (matches 0050 posture)
-- ---------------------------------------------------------------------------
revoke execute on function public.ask_current_day_key() from public, anon, authenticated;
grant execute on function public.ask_current_day_key() to service_role;
revoke execute on function public.ask_resolve_tier(uuid) from public, anon, authenticated;
grant execute on function public.ask_resolve_tier(uuid) to service_role;
revoke execute on function public.ask_daily_limit_for_tier(text) from public, anon, authenticated;
grant execute on function public.ask_daily_limit_for_tier(text) to service_role;
revoke execute on function public.ask_daily_used(uuid, text, inet, date) from public, anon, authenticated;
grant execute on function public.ask_daily_used(uuid, text, inet, date) to service_role;
revoke execute on function public.ask_quota_status(uuid, text, inet) from public, anon, authenticated;
grant execute on function public.ask_quota_status(uuid, text, inet) to service_role;
revoke execute on function public.reserve_ask_quota_daily(uuid, text, inet, text) from public, anon, authenticated;
grant execute on function public.reserve_ask_quota_daily(uuid, text, inet, text) to service_role;
revoke execute on function public.release_ask_reservation(uuid) from public, anon, authenticated;
grant execute on function public.release_ask_reservation(uuid) to service_role;
