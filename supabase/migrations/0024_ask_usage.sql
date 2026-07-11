-- M06-P03: Ask Vergeo usage rows, monthly spend aggregate, and atomic quota RPCs.
--
-- Reversible rollback:
--   DROP VIEW IF EXISTS public.ask_usage_monthly;
--   DROP FUNCTION IF EXISTS public.reset_ask_kill_switch(text);
--   DROP FUNCTION IF EXISTS public.finalize_ask_answer(uuid, integer, text, bigint);
--   DROP FUNCTION IF EXISTS public.reserve_ask_quota(uuid, text, inet, text);
--   DROP FUNCTION IF EXISTS public.guard_ask_usage_mutation();
--   DROP TABLE IF EXISTS public.ask_spend_monthly;
--   DROP TABLE IF EXISTS public.ask_usage;

-- ---------------------------------------------------------------------------
-- ask_usage — per-question rows (reserved before model call, finalized after)
-- ---------------------------------------------------------------------------
create table public.ask_usage (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users (id) on delete set null,
  guest_key text,
  client_ip inet,
  question_hash text,
  tokens integer not null default 0 check (tokens >= 0),
  usd_micros bigint not null default 0 check (usd_micros >= 0),
  model text,
  month_key text not null,
  status text not null default 'reserved'
    check (status in ('reserved', 'answered')),
  created_at timestamptz not null default timezone('utc', now()),
  answered_at timestamptz,
  check (
    user_id is not null
    or guest_key is not null
    or client_ip is not null
  )
);

create index ask_usage_user_month_idx
  on public.ask_usage (user_id, month_key)
  where user_id is not null;

create index ask_usage_guest_key_idx
  on public.ask_usage (guest_key)
  where guest_key is not null;

create index ask_usage_client_ip_idx
  on public.ask_usage (client_ip)
  where client_ip is not null;

create index ask_usage_month_key_idx
  on public.ask_usage (month_key);

create index ask_usage_question_hash_created_idx
  on public.ask_usage (question_hash, created_at desc)
  where question_hash is not null;

comment on table public.ask_usage is
  'Ask Vergeo per-question usage; reserved rows count toward quota before model call.';

comment on column public.ask_usage.client_ip is
  'Best-effort guest IP heuristic so lifetime guest quota survives device-cookie clears.';

-- ---------------------------------------------------------------------------
-- ask_spend_monthly — global monthly spend aggregate + kill-switch state
-- ---------------------------------------------------------------------------
create table public.ask_spend_monthly (
  month_key text primary key,
  total_usd_micros bigint not null default 0 check (total_usd_micros >= 0),
  killed_at timestamptz,
  admin_reset_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger ask_spend_monthly_set_updated_at
  before update on public.ask_spend_monthly
  for each row
  execute function public.set_updated_at();

comment on table public.ask_spend_monthly is
  'Global Ask Vergeo monthly USD spend (micro-dollars) and kill-switch latch.';

-- ---------------------------------------------------------------------------
-- Monthly aggregate view (M13-P09 dashboard tile reads this once live)
-- ---------------------------------------------------------------------------
create or replace view public.ask_usage_monthly as
select
  month_key,
  count(*) filter (where status = 'answered') as answered_count,
  coalesce(sum(tokens) filter (where status = 'answered'), 0)::bigint as total_tokens,
  coalesce(sum(usd_micros) filter (where status = 'answered'), 0)::bigint as total_usd_micros
from public.ask_usage
group by month_key;

comment on view public.ask_usage_monthly is
  'Per-month Ask Vergeo answered-question aggregates derived from ask_usage.';

-- ---------------------------------------------------------------------------
-- Per-model token rates (USD per 1M tokens) — config-driven spend meter
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description)
values (
  'ai_model_rates',
  '{"default": 0.15, "google/gemini-flash-1.5": 0.075, "openai/gpt-4o-mini": 0.15}'::jsonb,
  'Ask Vergeo model token rates: USD per 1M tokens (D23)'
)
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Service-role guard — block direct client mutations
-- ---------------------------------------------------------------------------
create or replace function public.guard_ask_usage_mutation()
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

  raise exception 'ask_usage is service-role only';
end;
$$;

create trigger ask_usage_guard_mutation
  before insert or update or delete on public.ask_usage
  for each row
  execute function public.guard_ask_usage_mutation();

create or replace function public.guard_ask_spend_monthly_mutation()
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

  raise exception 'ask_spend_monthly is service-role only';
end;
$$;

create trigger ask_spend_monthly_guard_mutation
  before insert or update or delete on public.ask_spend_monthly
  for each row
  execute function public.guard_ask_spend_monthly_mutation();

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
create or replace function public.ask_current_month_key()
returns text
language sql
stable
as $$
  select to_char(timezone('utc', now()), 'YYYY-MM');
$$;

create or replace function public.ask_read_config_int(p_key text, p_default integer)
returns integer
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_raw jsonb;
begin
  select value
  into v_raw
  from public.platform_config
  where key = p_key;

  if v_raw is null then
    return p_default;
  end if;

  if jsonb_typeof(v_raw) = 'number' then
    return (v_raw #>> '{}')::integer;
  end if;

  return coalesce((v_raw #>> '{}')::integer, p_default);
exception
  when others then
    return p_default;
end;
$$;

create or replace function public.ask_monthly_cap_usd_micros()
returns bigint
language sql
stable
security definer
set search_path = public
as $$
  select public.ask_read_config_int('ai_monthly_cap_usd', 15)::bigint * 1000000::bigint;
$$;

-- ---------------------------------------------------------------------------
-- Atomic quota reservation (check_and_reserve)
-- ---------------------------------------------------------------------------
create or replace function public.reserve_ask_quota(
  p_user_id uuid,
  p_guest_key text,
  p_client_ip inet,
  p_question_hash text
)
returns table (reservation_id uuid, allowed boolean, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_month_key text;
  v_guest_limit integer;
  v_free_limit integer;
  v_guest_count integer;
  v_free_count integer;
  v_reservation_id uuid;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'reserve_ask_quota requires service role';
  end if;

  v_month_key := public.ask_current_month_key();
  v_guest_limit := public.ask_read_config_int('ai_guest_quota', 3);
  v_free_limit := public.ask_read_config_int('ai_free_monthly_quota', 25);

  if p_user_id is not null then
    select count(*)
    into v_free_count
    from public.ask_usage au
    where au.user_id = p_user_id
      and au.month_key = v_month_key
      and au.status in ('reserved', 'answered');

    if v_free_count >= v_free_limit then
      allowed := false;
      reason := 'monthly_exceeded';
      reservation_id := null;
      return next;
      return;
    end if;
  else
    select count(*)
    into v_guest_count
    from public.ask_usage au
    where au.user_id is null
      and au.status in ('reserved', 'answered')
      and (
        (p_guest_key is not null and au.guest_key = p_guest_key)
        or (p_client_ip is not null and au.client_ip = p_client_ip)
      );

    if v_guest_count >= v_guest_limit then
      allowed := false;
      reason := 'guest_exceeded';
      reservation_id := null;
      return next;
      return;
    end if;
  end if;

  insert into public.ask_usage (
    user_id,
    guest_key,
    client_ip,
    question_hash,
    month_key,
    status
  )
  values (
    p_user_id,
    nullif(trim(p_guest_key), ''),
    p_client_ip,
    nullif(trim(p_question_hash), ''),
    v_month_key,
    'reserved'
  )
  returning id
  into v_reservation_id;

  allowed := true;
  reason := 'ok';
  reservation_id := v_reservation_id;
  return next;
end;
$$;

comment on function public.reserve_ask_quota(uuid, text, inet, text) is
  'Atomically reserves one Ask quota slot; guest lifetime keyed by guest_key OR client_ip (best-effort).';

-- ---------------------------------------------------------------------------
-- Finalize answered question + meter spend (record_answer)
-- ---------------------------------------------------------------------------
create or replace function public.finalize_ask_answer(
  p_reservation_id uuid,
  p_tokens integer,
  p_model text,
  p_usd_micros bigint
)
returns table (success boolean, month_total_usd_micros bigint, killed boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_month_key text;
  v_row public.ask_usage%rowtype;
  v_total bigint;
  v_cap bigint;
  v_killed boolean;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'finalize_ask_answer requires service role';
  end if;

  if p_tokens < 0 or p_usd_micros < 0 then
    raise exception 'token and spend values must be non-negative';
  end if;

  v_month_key := public.ask_current_month_key();

  select *
  into v_row
  from public.ask_usage au
  where au.id = p_reservation_id
  for update;

  if not found then
    success := false;
    month_total_usd_micros := 0;
    killed := false;
    return next;
    return;
  end if;

  if v_row.status = 'answered' then
    success := true;
    select coalesce(asm.total_usd_micros, 0)
    into month_total_usd_micros
    from public.ask_spend_monthly asm
    where asm.month_key = v_month_key;
    killed := coalesce(
      (
        select asm.killed_at is not null
          and (asm.admin_reset_at is null or asm.admin_reset_at < asm.killed_at)
        from public.ask_spend_monthly asm
        where asm.month_key = v_month_key
      ),
      false
    );
    return next;
    return;
  end if;

  update public.ask_usage au
  set
    tokens = p_tokens,
    usd_micros = p_usd_micros,
    model = nullif(trim(p_model), ''),
    status = 'answered',
    answered_at = timezone('utc', now())
  where au.id = p_reservation_id;

  insert into public.ask_spend_monthly as asm (month_key, total_usd_micros)
  values (v_month_key, p_usd_micros)
  on conflict (month_key)
  do update
    set total_usd_micros = asm.total_usd_micros + excluded.total_usd_micros
  returning asm.total_usd_micros
  into v_total;

  v_cap := public.ask_monthly_cap_usd_micros();

  if v_total >= v_cap then
    update public.ask_spend_monthly asm
    set killed_at = coalesce(asm.killed_at, timezone('utc', now()))
    where asm.month_key = v_month_key
      and asm.killed_at is null;
  end if;

  select asm.total_usd_micros,
    asm.killed_at is not null
      and (asm.admin_reset_at is null or asm.admin_reset_at < asm.killed_at)
  into v_total, v_killed
  from public.ask_spend_monthly asm
  where asm.month_key = v_month_key;

  success := true;
  month_total_usd_micros := coalesce(v_total, 0);
  killed := coalesce(v_killed, false);
  return next;
end;
$$;

comment on function public.finalize_ask_answer(uuid, integer, text, bigint) is
  'Idempotent finalize for a reserved Ask row; bumps monthly spend and may trip kill-switch.';

-- ---------------------------------------------------------------------------
-- Admin kill-switch reset
-- ---------------------------------------------------------------------------
create or replace function public.reset_ask_kill_switch(p_month_key text default null)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_month_key text;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'reset_ask_kill_switch requires service role';
  end if;

  v_month_key := coalesce(nullif(trim(p_month_key), ''), public.ask_current_month_key());

  insert into public.ask_spend_monthly (month_key)
  values (v_month_key)
  on conflict (month_key) do nothing;

  update public.ask_spend_monthly asm
  set
    killed_at = null,
    admin_reset_at = timezone('utc', now())
  where asm.month_key = v_month_key;

  return found;
end;
$$;

comment on function public.reset_ask_kill_switch(text) is
  'Admin-resettable kill-switch latch for the current (or specified) month.';

-- ---------------------------------------------------------------------------
-- RLS — service-role paths only; admin read on aggregates
-- ---------------------------------------------------------------------------
alter table public.ask_usage enable row level security;
alter table public.ask_spend_monthly enable row level security;

alter table public.ask_usage force row level security;
alter table public.ask_spend_monthly force row level security;

create policy ask_usage_select_admin
  on public.ask_usage
  for select
  to authenticated
  using (public.has_role('admin'));

create policy ask_spend_monthly_select_admin
  on public.ask_spend_monthly
  for select
  to authenticated
  using (public.has_role('admin'));

grant select on public.ask_usage to authenticated;
grant select on public.ask_spend_monthly to authenticated;
grant select on public.ask_usage_monthly to authenticated;
