-- Convergeo Intelligence 1B-03: authoritative commercial metrics (docs/plan/intelligence/stage1-plan.md §R-I).
--
-- Additive: one new function, analytics_commercial_daily(from, to), and a CREATE OR REPLACE
-- of analytics_rollup_day (1B-01, same signature) that additionally stores the day's
-- commercial metrics. Nothing calls either function until `analytics_v2_rollups` is ON.
--
-- Paid orders and GMV are derived ONLY from orders, order_items, checkout_groups and
-- payments — never from analytics events or funnel_events snapshots. Money is integer
-- ngwee (bigint sums of qty * unit_price_ngwee + delivery_fee_ngwee).
--
-- Down (manual, after analytics_v2_rollups is OFF and the 1B-03 code is reverted):
--   re-run the analytics_rollup_day definition from 20261113235100_analytics_rollups.sql;
--   drop function if exists public.analytics_commercial_daily(date, date);

-- ---------------------------------------------------------------------------
-- Authoritative commercial metrics (plan §R-I)
-- ---------------------------------------------------------------------------
--
-- Attribution: an order belongs to the UTC day of orders.created_at; a checkout belongs
-- to the UTC day of checkout_groups.created_at. A checkout group is PAID when it has a
-- payment with status 'success' (payments.status is the authoritative, terminal-winning
-- state, see services/payments/state.py). An order is paid when its checkout group is.
--
-- Reconciliation (data quality, never "fixed" here): for the checkout groups whose orders
-- were placed that day, the number of successful payments must equal the number of paid
-- groups (one success per group) and the sum of successful payment amounts must equal the
-- sum of those groups' total_ngwee.

create or replace function public.analytics_commercial_daily(p_from date, p_to date)
returns table (
  day date,
  checkouts_started bigint,
  orders_placed bigint,
  orders_cancelled bigint,
  orders_paid bigint,
  paid_checkouts bigint,
  payments_succeeded bigint,
  payments_succeeded_ngwee bigint,
  paid_checkout_total_ngwee bigint,
  gmv_paid_ngwee bigint
)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  with days as (
    select d::date as day
    from generate_series(p_from, p_to, interval '1 day') as d
  ),
  order_rows as (
    select
      (o.created_at at time zone 'UTC')::date as day,
      o.id,
      o.checkout_group_id,
      o.status,
      o.delivery_fee_ngwee
        + coalesce((
          select sum(oi.qty::bigint * oi.unit_price_ngwee)
          from public.order_items oi
          where oi.order_id = o.id
        ), 0) as order_total_ngwee
    from public.orders o
    where o.created_at >= (p_from::timestamp at time zone 'UTC')
      and o.created_at < ((p_to + 1)::timestamp at time zone 'UTC')
  ),
  group_pay as (
    select
      p.checkout_group_id,
      count(*) as successes,
      sum(p.amount_ngwee) as success_ngwee
    from public.payments p
    where p.status = 'success'
      and p.checkout_group_id in (select checkout_group_id from order_rows)
    group by p.checkout_group_id
  ),
  day_groups as (
    select distinct r.day, r.checkout_group_id
    from order_rows r
  ),
  paid_groups as (
    select
      dg.day,
      count(*) as paid_checkouts,
      sum(gp.successes) as payments_succeeded,
      sum(gp.success_ngwee) as payments_succeeded_ngwee,
      sum(cg.total_ngwee) as paid_checkout_total_ngwee
    from day_groups dg
    join group_pay gp on gp.checkout_group_id = dg.checkout_group_id
    join public.checkout_groups cg on cg.id = dg.checkout_group_id
    group by dg.day
  ),
  order_agg as (
    select
      r.day,
      count(*) as orders_placed,
      count(*) filter (where r.status = 'cancelled') as orders_cancelled,
      count(*) filter (where gp.checkout_group_id is not null) as orders_paid,
      coalesce(sum(r.order_total_ngwee) filter (
        where gp.checkout_group_id is not null and r.status <> 'cancelled'
      ), 0) as gmv_paid_ngwee
    from order_rows r
    left join group_pay gp on gp.checkout_group_id = r.checkout_group_id
    group by r.day
  ),
  checkout_agg as (
    select (cg.created_at at time zone 'UTC')::date as day, count(*) as checkouts_started
    from public.checkout_groups cg
    where cg.created_at >= (p_from::timestamp at time zone 'UTC')
      and cg.created_at < ((p_to + 1)::timestamp at time zone 'UTC')
    group by 1
  )
  select
    d.day,
    coalesce(c.checkouts_started, 0)::bigint,
    coalesce(oa.orders_placed, 0)::bigint,
    coalesce(oa.orders_cancelled, 0)::bigint,
    coalesce(oa.orders_paid, 0)::bigint,
    coalesce(pg.paid_checkouts, 0)::bigint,
    coalesce(pg.payments_succeeded, 0)::bigint,
    coalesce(pg.payments_succeeded_ngwee, 0)::bigint,
    coalesce(pg.paid_checkout_total_ngwee, 0)::bigint,
    coalesce(oa.gmv_paid_ngwee, 0)::bigint
  from days d
  left join checkout_agg c on c.day = d.day
  left join order_agg oa on oa.day = d.day
  left join paid_groups pg on pg.day = d.day
  order by d.day;
$$;

comment on function public.analytics_commercial_daily(date, date) is
  'Convergeo Intelligence 1B-03: per-UTC-day checkouts, orders, paid orders, successful '
  'payments and paid GMV (integer ngwee) from orders/order_items/checkout_groups/payments '
  'only. The single definition shared by the rollup and the admin API.';

revoke all on function public.analytics_commercial_daily(date, date) from public, anon, authenticated;
grant execute on function public.analytics_commercial_daily(date, date) to service_role;

-- ---------------------------------------------------------------------------
-- Daily rollup, now including commercial metrics (same signature as 1B-01)
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
  'Convergeo Intelligence 1B-01/1B-03: idempotent recompute of one UTC day of analytics rollups '
  '(delete + insert under a per-day advisory lock). Sessionises by a > p_idle_minutes idle '
  'gap; session end is an estimate (last_seen). Run by the flag-gated API rollup tick with '
  'SET LOCAL statement_timeout.';

revoke all on function public.analytics_rollup_day(date, integer) from public, anon, authenticated;
grant execute on function public.analytics_rollup_day(date, integer) to service_role;
