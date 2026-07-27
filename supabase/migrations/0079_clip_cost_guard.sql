-- M17-P08 — monthly clip cost accounting + the upload kill switch.
--
-- Mirrors the Ask-Vergeo spend table (0031) rather than reusing it: the two
-- guards bound different budgets, and sharing a row would mean an AI overspend
-- paused video uploads (and vice versa). Separate tables keep each kill switch
-- honest about what it is actually protecting.
--
-- Money is INTEGER MICRO-USD throughout (convention #1's rule applied to a cost
-- path): no float, no numeric-with-scale surprises, and every read is exact.
--
-- The switch trips inside `clip_record_spend`, in the same statement that adds
-- the spend, so there is no window where the cap is exceeded but the switch is
-- still open. It is reversed by RECORDING a reset rather than by clearing
-- `killed_at` — an auditor must be able to see that it tripped and that an
-- operator reversed it, which a destructive reset would erase.
--
-- Reversible: drop the two functions and the table, and delete the two config
-- rows.

-- ---------------------------------------------------------------------------
-- Monthly accounting
-- ---------------------------------------------------------------------------
create table public.clip_spend_monthly (
  month_key text primary key check (month_key ~ '^[0-9]{4}-[0-9]{2}$'),
  total_usd_micros bigint not null default 0 check (total_usd_micros >= 0),
  clips_transcoded integer not null default 0 check (clips_transcoded >= 0),
  bytes_served bigint not null default 0 check (bytes_served >= 0),
  killed_at timestamptz,
  admin_reset_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.clip_spend_monthly is
  'M17-P08 monthly video cost accounting in integer micro-USD. killed_at trips the upload kill switch; admin_reset_at newer than killed_at re-opens the month (history preserved).';

create trigger clip_spend_monthly_set_updated_at
  before update on public.clip_spend_monthly
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS — admin read only; no client write path at all.
-- ---------------------------------------------------------------------------
alter table public.clip_spend_monthly enable row level security;
alter table public.clip_spend_monthly force row level security;

create policy clip_spend_monthly_admin_select
  on public.clip_spend_monthly
  for select
  to authenticated
  using (public.has_role('admin'));

grant select on public.clip_spend_monthly to authenticated;
-- Deliberately no insert/update/delete grant to any client role: the only write
-- path is the SECURITY DEFINER function below, executable by service_role only.

-- ---------------------------------------------------------------------------
-- Atomic spend recording + cap enforcement
-- ---------------------------------------------------------------------------
create or replace function public.clip_record_spend(
  p_month_key text,
  p_usd_micros bigint,
  p_clips integer,
  p_bytes bigint,
  p_cap_usd_micros bigint
)
returns bigint
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  new_total bigint;
begin
  if p_month_key !~ '^[0-9]{4}-[0-9]{2}$' then
    raise exception 'clip_record_spend: invalid month key %', p_month_key
      using errcode = 'check_violation';
  end if;

  -- Relative increment, not read-then-write: two concurrent transcode callbacks
  -- must both count. Losing spend is the one direction a cost guard must never
  -- round toward.
  insert into public.clip_spend_monthly (month_key, total_usd_micros, clips_transcoded, bytes_served)
  values (p_month_key, greatest(0, p_usd_micros), greatest(0, p_clips), greatest(0, p_bytes))
  on conflict (month_key) do update
    set total_usd_micros = public.clip_spend_monthly.total_usd_micros + greatest(0, p_usd_micros),
        clips_transcoded = public.clip_spend_monthly.clips_transcoded + greatest(0, p_clips),
        bytes_served = public.clip_spend_monthly.bytes_served + greatest(0, p_bytes)
  returning total_usd_micros into new_total;

  -- Trip in the SAME statement chain as the spend that caused it, so there is no
  -- window where the cap is exceeded but the switch is still open.
  if p_cap_usd_micros > 0 and new_total >= p_cap_usd_micros then
    update public.clip_spend_monthly
       set killed_at = coalesce(killed_at, now())
     where month_key = p_month_key;
  end if;

  return new_total;
end;
$$;

comment on function public.clip_record_spend(text, bigint, integer, bigint, bigint) is
  'M17-P08 atomic monthly clip spend increment. Trips the upload kill switch in the same call when the cap is reached. Relative increment so concurrent callbacks cannot lose spend.';

revoke all on function public.clip_record_spend(text, bigint, integer, bigint, bigint) from public;
grant execute on function public.clip_record_spend(text, bigint, integer, bigint, bigint) to service_role;

-- ---------------------------------------------------------------------------
-- Operator reversal — recorded, never destructive
-- ---------------------------------------------------------------------------
create or replace function public.reset_clip_kill_switch(p_month_key text)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  affected integer;
begin
  update public.clip_spend_monthly
     set admin_reset_at = now()
   where month_key = p_month_key
     and killed_at is not null;
  get diagnostics affected = row_count;
  return affected > 0;
end;
$$;

comment on function public.reset_clip_kill_switch(text) is
  'M17-P08 operator reversal of the clip upload kill switch. Records admin_reset_at rather than clearing killed_at, so the trip stays visible in the history.';

revoke all on function public.reset_clip_kill_switch(text) from public;
grant execute on function public.reset_clip_kill_switch(text) to service_role;

-- ---------------------------------------------------------------------------
-- Config — cap and unit rates, both operator-editable with no deploy.
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  (
    'clip_monthly_cap_usd',
    '10'::jsonb,
    'M17-P08 monthly video cost ceiling in whole USD. Sits inside the $50/mo infrastructure budget alongside ai_monthly_cap_usd. Reaching it pauses uploads; the feed keeps serving posters.'
  ),
  (
    'clip_cost_rates',
    '{"transcode_per_clip": "0.02", "delivery_per_gb": "0.08"}'::jsonb,
    'M17-P08 unit costs in USD, read as Decimal and converted to integer micro-USD. Reconcile against the Cloudinary invoice monthly; a >15% drift means these are wrong.'
  )
on conflict (key) do nothing;
