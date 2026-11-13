-- Convergeo Intelligence 1B-06 / founder decisions OD-6 + OD-8 (12 Nov 2026):
-- the search-term k-threshold counts DISTINCT anonymous sessions, not searches.
-- (docs/plan/intelligence/stage1-plan.md §R-E, Stage 1B decisions.)
--
-- Additive only:
--   * search_query_log.analytics_session_id uuid NULL — the same rotating, anonymous v2
--     session id the analytics client already sends (localStorage `vg_sess2`, 30-minute
--     idle rotation, packages/analytics/src/v2/ids.ts). No PII and no user id. It is
--     written by the search API only when analytics_v2_collect is ON and the client
--     sends `X-Analytics-Session`; it is never used for authorization. The 30-day
--     search-log PII trim NULLs it together with user_id.
--   * analytics_search_daily.unsessioned_searches integer NOT NULL DEFAULT 0 — searches
--     of the term/day that carried no session id.
--   * analytics_rollup_day redefined (same signature): sessions is now
--     count(DISTINCT analytics_session_id) (0 when none) instead of NULL.
--
-- k rule (admin API, analytics_search_daily_purge): a term's session count over a window
-- is greatest(sum(sessions), 1 if any row has unsessioned searches or a legacy NULL
-- sessions value else 0). One person repeating a term 5 times = 1 session < k = 5, and
-- session-less rows can never contribute more than one session in total.
--
-- RLS: no new table. search_query_log and analytics_search_daily keep FORCE RLS with
-- admin-select / service_role-all policies, so the new columns inherit them; anon has no
-- grant on either table.
--
-- Down (manual, after analytics_v2_rollups is OFF and the 1B-06 code is reverted):
--   re-run the analytics_rollup_day definition from 20261112140000_analytics_commercial.sql;
--   alter table public.analytics_search_daily drop column if exists unsessioned_searches;
--   alter table public.search_query_log drop column if exists analytics_session_id;
-- Dropping the columns loses only the session attribution (aggregates stay valid; the
-- admin k rule then treats every row as session-less, i.e. stricter).

alter table public.search_query_log
  add column if not exists analytics_session_id uuid;

comment on column public.search_query_log.analytics_session_id is
  'Anonymous rotating analytics_v2 session id (30-min idle, client-generated, no PII). '
  'Only set when analytics_v2_collect is ON and the client sends it; never used for '
  'authz. NULLed after 30 days by the search-log PII trim. Used for the distinct-session '
  'k-threshold (OD-8).';

alter table public.analytics_search_daily
  add column if not exists unsessioned_searches integer not null default 0
    check (unsessioned_searches >= 0);

comment on column public.analytics_search_daily.sessions is
  'Distinct anonymous analytics sessions that searched the term that day (OD-8). NULL '
  'only on rows computed before 20261112150000 (treated as session-less by readers).';
comment on column public.analytics_search_daily.unsessioned_searches is
  'Searches of the term that day without a session id. Readers count all of them, across '
  'the whole window, as at most ONE session (OD-8), so one person cannot pass k.';

-- ---------------------------------------------------------------------------
-- Daily rollup with distinct-session search demand (same signature as 1B-01)
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

  -- Commercial metrics — authoritative tables only (plan §R-I).
  insert into public.analytics_daily_rollup (day, metric, value, sample_n)
  select p_day, m.metric, m.value, m.sample_n
  from public.analytics_commercial_daily(p_day, p_day) c
  cross join lateral (
    values
      ('checkouts_started', c.checkouts_started, c.checkouts_started::int),
      ('orders_placed', c.orders_placed, c.orders_placed::int),
      ('orders_cancelled', c.orders_cancelled, c.orders_placed::int),
      ('orders_paid', c.orders_paid, c.orders_placed::int),
      ('paid_checkouts', c.paid_checkouts, c.paid_checkouts::int),
      ('payments_succeeded', c.payments_succeeded, c.payments_succeeded::int),
      ('payments_succeeded_ngwee', c.payments_succeeded_ngwee, c.payments_succeeded::int),
      ('gmv_paid_ngwee', c.gmv_paid_ngwee, c.orders_paid::int),
      (
        'dq_payment_mismatch',
        case
          when c.payments_succeeded <> c.paid_checkouts
            or c.payments_succeeded_ngwee <> c.paid_checkout_total_ngwee then 1
          else 0
        end::bigint,
        c.paid_checkouts::int
      )
  ) as m(metric, value, sample_n);
  get diagnostics v_n = row_count;
  v_rows := v_rows + v_n;

  -- Search demand per redacted, normalized term (search_query_log, kind = 'search').
  -- OD-8: sessions = DISTINCT anonymous analytics sessions; rows without a session
  -- (legacy, no-JS, counts-only) are counted in unsessioned_searches and readers treat
  -- them as at most ONE session, so one person can never pass k by repeating a term.
  insert into public.analytics_search_daily (
    day, normalized_term, searches, zero_results, sessions, unsessioned_searches
  )
  select
    p_day,
    left(q.normalized_term, 120),
    count(*)::int,
    count(*) filter (where q.zero_result)::int,
    count(distinct q.analytics_session_id)::int,
    count(*) filter (where q.analytics_session_id is null)::int
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
  'Convergeo Intelligence 1B-01/1B-03/OD-8: idempotent recompute of one UTC day of analytics rollups '
  '(delete + insert under a per-day advisory lock). Sessionises by a > p_idle_minutes idle '
  'gap; session end is an estimate (last_seen). Run by the flag-gated API rollup tick with '
  'SET LOCAL statement_timeout.';

revoke all on function public.analytics_rollup_day(date, integer) from public, anon, authenticated;
grant execute on function public.analytics_rollup_day(date, integer) to service_role;
