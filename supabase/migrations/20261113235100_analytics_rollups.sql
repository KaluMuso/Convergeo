-- Convergeo Intelligence 1B-01: daily analytics rollups (docs/plan/intelligence/stage1-plan.md §1B).
--
-- Additive only: three new tables and one new function. No existing table, view,
-- function or policy is touched, and nothing calls these objects until the
-- `analytics_v2_rollups` feature flag (1A-02, default OFF) is switched on, so merging
-- this migration changes no behaviour.
--
-- Objects
--   analytics_daily_rollup   long-format daily metrics (day, metric, dim_key, dim_value,
--                            value, sample_n). Profile/segment features later become new
--                            metrics here, not new tables (plan §F.5).
--   analytics_search_daily   per-day per-normalized-term search demand. Terms are the
--                            REDACTED + normalized form (1A-06); k-thresholds (plan §R-E)
--                            are applied at read time by the admin API, never stored raw.
--   analytics_rollup_runs    audit of every rollup attempt (ok / error) per day.
--   analytics_rollup_day(day) idempotent recompute of one UTC day (delete + insert under a
--                            per-day advisory lock). Called by the API rollup tick with
--                            SET LOCAL statement_timeout, off the request path.
--
-- Sessionisation (plan §R-A): within one client session_id, events are ordered by
-- coalesce(client_ts, received_at); a gap of MORE than 30 minutes starts a new derived
-- session. A session's end is never observed: estimated_end = last_seen and duration is
-- reported as the "active span" (last_seen - first_seen). A session with at most one
-- interaction (events other than session_start) counts as a bounce. Counts-only rows
-- (opt-out / GPC: NULL session_id) count towards event totals but never towards sessions.
-- A session that spans UTC midnight is counted on each day it has events (documented).
--
-- Day boundaries are UTC (same as the retention ticks). Money is integer ngwee (bigint).
--
-- RLS: FORCE on every table. Admin read (authenticated + has_role('admin')), service_role
-- write; anon has no grant. Functions are SECURITY DEFINER with a pinned search_path and
-- EXECUTE granted to service_role only.
--
-- Down (manual, run only after analytics_v2_rollups is OFF and the 1B code is reverted):
--   drop function if exists public.analytics_rollup_day(date, integer);
--   drop table if exists public.analytics_rollup_runs;
--   drop table if exists public.analytics_search_daily;
--   drop table if exists public.analytics_daily_rollup;
-- The tables hold only derived aggregates: they are recomputable from raw data for the
-- 30-day raw window, so dropping them loses only older history.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table if not exists public.analytics_daily_rollup (
  day date not null,
  metric text not null check (metric ~ '^[a-z][a-z0-9_]{0,63}$'),
  dim_key text not null default '' check (char_length(dim_key) <= 32),
  dim_value text not null default '' check (char_length(dim_value) <= 64),
  value bigint not null,
  sample_n integer not null default 0 check (sample_n >= 0),
  computed_at timestamptz not null default timezone('utc', now()),
  primary key (day, metric, dim_key, dim_value)
);

comment on table public.analytics_daily_rollup is
  'Convergeo Intelligence 1B: long-format daily metrics recomputed by analytics_rollup_day(). '
  'Behavioural metrics come from analytics_event_log; commercial metrics (1B-03) only from '
  'orders/payments. Money values are integer ngwee. Admin read, service_role write.';
comment on column public.analytics_daily_rollup.sample_n is
  'Underlying sample size (e.g. sessions) so readers can apply the minimum-n rule (plan §R-E).';

create table if not exists public.analytics_search_daily (
  day date not null,
  normalized_term text not null check (char_length(normalized_term) between 1 and 120),
  searches integer not null check (searches >= 0),
  zero_results integer not null check (zero_results >= 0),
  sessions integer check (sessions is null or sessions >= 0),
  computed_at timestamptz not null default timezone('utc', now()),
  primary key (day, normalized_term)
);

comment on table public.analytics_search_daily is
  'Convergeo Intelligence 1B: daily search demand per redacted, normalized term. '
  'sessions is NULL while search_query_log carries no session link (k-threshold then '
  'falls back to searches). Never exposed below k (admin API). Admin read, service_role write.';

create table if not exists public.analytics_rollup_runs (
  day date not null,
  started_at timestamptz not null default clock_timestamp(),
  finished_at timestamptz,
  status text not null check (status in ('ok', 'error')),
  rows integer not null default 0 check (rows >= 0),
  error text check (error is null or char_length(error) <= 500),
  primary key (day, started_at)
);

comment on table public.analytics_rollup_runs is
  'Convergeo Intelligence 1B: one row per rollup attempt per day (ok rows written by '
  'analytics_rollup_day in the same transaction; error rows by the API tick).';

-- ---------------------------------------------------------------------------
-- RLS — admin read, service_role write, anon nothing
-- ---------------------------------------------------------------------------

alter table public.analytics_daily_rollup enable row level security;
alter table public.analytics_daily_rollup force row level security;
alter table public.analytics_search_daily enable row level security;
alter table public.analytics_search_daily force row level security;
alter table public.analytics_rollup_runs enable row level security;
alter table public.analytics_rollup_runs force row level security;

drop policy if exists analytics_daily_rollup_admin_select on public.analytics_daily_rollup;
create policy analytics_daily_rollup_admin_select
  on public.analytics_daily_rollup for select to authenticated
  using (public.has_role('admin'));
drop policy if exists analytics_daily_rollup_service_role_all on public.analytics_daily_rollup;
create policy analytics_daily_rollup_service_role_all
  on public.analytics_daily_rollup for all to service_role
  using (true) with check (true);

drop policy if exists analytics_search_daily_admin_select on public.analytics_search_daily;
create policy analytics_search_daily_admin_select
  on public.analytics_search_daily for select to authenticated
  using (public.has_role('admin'));
drop policy if exists analytics_search_daily_service_role_all on public.analytics_search_daily;
create policy analytics_search_daily_service_role_all
  on public.analytics_search_daily for all to service_role
  using (true) with check (true);

drop policy if exists analytics_rollup_runs_admin_select on public.analytics_rollup_runs;
create policy analytics_rollup_runs_admin_select
  on public.analytics_rollup_runs for select to authenticated
  using (public.has_role('admin'));
drop policy if exists analytics_rollup_runs_service_role_all on public.analytics_rollup_runs;
create policy analytics_rollup_runs_service_role_all
  on public.analytics_rollup_runs for all to service_role
  using (true) with check (true);

revoke all on table public.analytics_daily_rollup from public, anon, authenticated;
revoke all on table public.analytics_search_daily from public, anon, authenticated;
revoke all on table public.analytics_rollup_runs from public, anon, authenticated;
grant select on table public.analytics_daily_rollup to authenticated;
grant select on table public.analytics_search_daily to authenticated;
grant select on table public.analytics_rollup_runs to authenticated;
grant select, insert, update, delete on table public.analytics_daily_rollup to service_role;
grant select, insert, update, delete on table public.analytics_search_daily to service_role;
grant select, insert, update, delete on table public.analytics_rollup_runs to service_role;

-- ---------------------------------------------------------------------------
-- Daily rollup
-- ---------------------------------------------------------------------------

create or replace function public.analytics_rollup_day(p_day date, p_idle_minutes integer default 30)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_from timestamptz;
  v_to timestamptz;
  v_rows integer := 0;
  v_n integer;
  v_started timestamptz := clock_timestamp();
begin
  if p_day is null then
    raise exception 'analytics_rollup_day: day is required';
  end if;
  if p_day > timezone('utc', now())::date then
    raise exception 'analytics_rollup_day: % is in the future', p_day;
  end if;
  if p_idle_minutes is null or p_idle_minutes < 1 or p_idle_minutes > 240 then
    raise exception 'analytics_rollup_day: idle minutes out of range';
  end if;

  v_from := p_day::timestamp at time zone 'UTC';
  v_to := (p_day + 1)::timestamp at time zone 'UTC';

  -- One recompute per day at a time (two API workers / a manual re-run).
  perform pg_advisory_xact_lock(hashtext('analytics_rollup_day'), p_day - date '2000-01-01');

  delete from public.analytics_daily_rollup where day = p_day;
  delete from public.analytics_search_daily where day = p_day;

  -- Events of the day (BRIN range on received_at).
  drop table if exists pg_temp._ar_ev;
  create temp table _ar_ev on commit drop as
  select
    e.session_id,
    e.anon_id,
    e.event_name,
    e.page_key,
    e.entity_type,
    e.entity_id,
    e.props,
    coalesce(e.client_ts, e.received_at) as ts
  from public.analytics_event_log e
  where e.received_at >= v_from and e.received_at < v_to;

  -- Derived sessions: split a client session on an idle gap > p_idle_minutes.
  drop table if exists pg_temp._ar_sess_ev;
  create temp table _ar_sess_ev on commit drop as
  select
    g.*,
    sum(g.is_new) over (
      partition by g.session_id order by g.ts, g.event_name
      rows between unbounded preceding and current row
    ) as part
  from (
    select
      ev.*,
      case
        when lag(ev.ts) over w is null then 1
        when ev.ts - lag(ev.ts) over w > make_interval(mins => p_idle_minutes) then 1
        else 0
      end as is_new
    from _ar_ev ev
    where ev.session_id is not null
    window w as (partition by ev.session_id order by ev.ts, ev.event_name)
  ) g;

  drop table if exists pg_temp._ar_sess;
  create temp table _ar_sess on commit drop as
  select
    s.session_id,
    s.part,
    (array_agg(s.anon_id order by s.ts))[1] as anon_id,
    min(s.ts) as first_seen,
    max(s.ts) as last_seen,
    count(*) filter (where s.event_name <> 'session_start') as interactions,
    (array_agg(s.page_key order by s.ts) filter (where s.page_key is not null))[1] as entry_page,
    bool_or(s.event_name = 'product_view') as has_product_view,
    bool_or(s.event_name = 'search') as has_search
  from _ar_sess_ev s
  group by s.session_id, s.part;

  -- Session metrics. estimated_end = last_seen (never observed); duration = active span.
  insert into public.analytics_daily_rollup (day, metric, value, sample_n)
  select p_day, m.metric, m.value, m.sample_n
  from (
    select 'sessions'::text as metric, count(*)::bigint as value, count(*)::int as sample_n
    from _ar_sess
    union all
    select 'bounced_sessions', count(*) filter (where interactions <= 1), count(*)::int
    from _ar_sess
    union all
    select 'visitors', count(distinct anon_id), count(*)::int
    from _ar_sess
    union all
    select
      'active_span_seconds_total',
      coalesce(sum(floor(extract(epoch from (last_seen - first_seen))))::bigint, 0),
      count(*)::int
    from _ar_sess
    union all
    select
      'active_span_seconds_p50',
      coalesce(
        (percentile_disc(0.5) within group (
          order by floor(extract(epoch from (last_seen - first_seen)))
        ))::bigint,
        0
      ),
      count(*)::int
    from _ar_sess
    union all
    select 'searches', count(*), count(distinct session_id)::int
    from _ar_ev where event_name = 'search'
    union all
    select
      'zero_result_searches',
      count(*) filter (where props ->> 'zero_result' = 'true'),
      count(*)::int
    from _ar_ev where event_name = 'search'
  ) m;
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Funnel, upper (behavioural) steps: sessions reaching each step.
  insert into public.analytics_daily_rollup (day, metric, dim_key, dim_value, value, sample_n)
  select p_day, 'funnel_sessions', 'step', f.step, f.value, f.sample_n
  from (
    select 'session'::text as step, count(*)::bigint as value, count(*)::int as sample_n
    from _ar_sess
    union all
    select 'search', count(*) filter (where has_search), count(*)::int from _ar_sess
    union all
    select 'product_view', count(*) filter (where has_product_view), count(*)::int from _ar_sess
  ) f;
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Events by name (includes counts-only rows).
  insert into public.analytics_daily_rollup (day, metric, dim_key, dim_value, value, sample_n)
  select p_day, 'events', 'event_name', event_name, count(*), count(distinct session_id)::int
  from _ar_ev
  group by event_name;
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Page views by page template.
  insert into public.analytics_daily_rollup (day, metric, dim_key, dim_value, value, sample_n)
  select p_day, 'page_views', 'page_key', coalesce(page_key, 'other'), count(*),
         count(distinct session_id)::int
  from _ar_ev
  where event_name = 'page_view'
  group by coalesce(page_key, 'other');
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Session entry pages.
  insert into public.analytics_daily_rollup (day, metric, dim_key, dim_value, value, sample_n)
  select p_day, 'session_entries', 'page_key', coalesce(entry_page, 'other'), count(*),
         count(*)::int
  from _ar_sess
  group by coalesce(entry_page, 'other');
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Product views by product entity.
  insert into public.analytics_daily_rollup (day, metric, dim_key, dim_value, value, sample_n)
  select p_day, 'product_views', 'product_id', entity_id::text, count(*),
         count(distinct session_id)::int
  from _ar_ev
  where event_name = 'product_view' and entity_type = 'product' and entity_id is not null
  group by entity_id;
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Server-side cart adds (funnel_events, no session link).
  insert into public.analytics_daily_rollup (day, metric, value, sample_n)
  select p_day, 'funnel_cart_adds', count(*), count(*)::int
  from public.funnel_events fe
  where fe.stage = 'cart_add' and fe.created_at >= v_from and fe.created_at < v_to;
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Search demand per redacted, normalized term (search_query_log, kind = 'search').
  insert into public.analytics_search_daily (day, normalized_term, searches, zero_results, sessions)
  select
    p_day,
    left(q.normalized_term, 120),
    count(*)::int,
    count(*) filter (where q.zero_result)::int,
    null::int
  from public.search_query_log q
  where q.kind = 'search'
    and q.created_at >= v_from and q.created_at < v_to
    and char_length(btrim(q.normalized_term)) > 0
  group by left(q.normalized_term, 120);
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  insert into public.analytics_rollup_runs (day, started_at, finished_at, status, rows)
  values (p_day, v_started, clock_timestamp(), 'ok', v_rows);

  return v_rows;
end;
$$;

comment on function public.analytics_rollup_day(date, integer) is
  'Convergeo Intelligence 1B-01: idempotent recompute of one UTC day of analytics rollups '
  '(delete + insert under a per-day advisory lock). Sessionises by a > p_idle_minutes idle '
  'gap; session end is an estimate (last_seen). Run by the flag-gated API rollup tick with '
  'SET LOCAL statement_timeout.';

revoke all on function public.analytics_rollup_day(date, integer) from public, anon, authenticated;
grant execute on function public.analytics_rollup_day(date, integer) to service_role;
