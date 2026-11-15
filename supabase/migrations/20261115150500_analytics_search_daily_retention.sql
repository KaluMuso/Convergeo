-- Convergeo Intelligence 1B-06 / founder decision OD-10 (12 Nov 2026): retention for
-- analytics_search_daily (docs/plan/intelligence/stage1-plan.md, Stage 1B decisions).
--
-- Additive: one new function. Nothing calls it until the flag-gated v2 retention tick
-- (POST /internal/analytics/v2-retention-tick, `analytics_v2_rollups`, default OFF).
--
-- Rule (days are Africa/Lusaka reporting days, OD-9):
--   * below-k terms: a row older than 30 days is deleted unless its term met k in the
--     row's calendar month;
--   * terms that met k: kept for 13 whole months, then deleted — a calendar month is
--     dropped as a unit once it started more than 13 months before the current month
--     (so a row lives 13 to 14 months).
-- "Met k" is the admin k rule (OD-6/OD-8, admin_analytics.SEARCH_K_MEASURE_SQL) over the
-- calendar month: greatest(sum(sessions), 1 if any row is session-less else 0) >= k, with
-- k = platform_config.analytics_term_k_min floored at 5. A month is complete by the time
-- any of its rows is 30 days old (months are <= 31 days), so the decision sees the whole
-- month; deleting below-k rows can only lower that month's measure further, so batches
-- and re-runs are consistent.
--
-- Batched: each call deletes at most p_limit rows (oldest first) and returns the count;
-- the API loops until a call returns < p_limit (same pattern as the 1A-07 dedup purge).
-- Idempotent: a second run deletes nothing.
--
-- RLS: no new table. SECURITY DEFINER with a pinned search_path; EXECUTE for
-- service_role only.
--
-- Down (manual, after the 1B-06 retention wiring is reverted):
--   drop function if exists public.analytics_search_daily_purge(date, integer);
-- Rows already deleted are not recoverable from the table itself; they are recomputable
-- from search_query_log only for days still inside that log's retention.

create or replace function public.analytics_search_daily_purge(
  p_today date,
  p_limit integer default 5000
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_k integer;
  v_below_k_before date;
  v_expire_before date;
  v_n integer;
begin
  if p_today is null then
    raise exception 'analytics_search_daily_purge: today is required';
  end if;
  if p_limit is null or p_limit < 1 or p_limit > 50000 then
    raise exception 'analytics_search_daily_purge: limit out of range';
  end if;

  select greatest(
    5,
    coalesce(max(case when (c.value #>> '{}') ~ '^[0-9]{1,6}$'
                      then (c.value #>> '{}')::integer end), 5)
  )
  into v_k
  from public.platform_config c
  where c.key = 'analytics_term_k_min';

  v_below_k_before := p_today - 30;
  v_expire_before := (date_trunc('month', p_today::timestamp) - interval '13 months')::date;

  with month_k as (
    select s.normalized_term, date_trunc('month', s.day::timestamp)::date as month
    from public.analytics_search_daily s
    where s.day < date_trunc('month', p_today::timestamp)::date
    group by 1, 2
    having greatest(
      coalesce(sum(s.sessions), 0),
      max(case when s.sessions is null or s.unsessioned_searches > 0 then 1 else 0 end)
    ) >= v_k
  ),
  doomed as (
    select s.day, s.normalized_term
    from public.analytics_search_daily s
    where s.day < v_expire_before
       or (
         s.day < v_below_k_before
         and not exists (
           select 1
           from month_k m
           where m.normalized_term = s.normalized_term
             and m.month = date_trunc('month', s.day::timestamp)::date
         )
       )
    order by s.day, s.normalized_term
    limit p_limit
  )
  delete from public.analytics_search_daily s
  using doomed d
  where s.day = d.day and s.normalized_term = d.normalized_term;
  get diagnostics v_n = row_count;
  return v_n;
end;
$$;

comment on function public.analytics_search_daily_purge(date, integer) is
  'Convergeo Intelligence OD-10: deletes analytics_search_daily rows older than 30 days '
  'whose term did not meet k (distinct sessions, OD-8) in that calendar month, and every '
  'row of a month that started more than 13 months before p_today''s month. At most '
  'p_limit rows per call; idempotent. Run by the flag-gated v2 retention tick.';

revoke all on function public.analytics_search_daily_purge(date, integer)
  from public, anon, authenticated;
grant execute on function public.analytics_search_daily_purge(date, integer) to service_role;
