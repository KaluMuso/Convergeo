-- Fix Ask Vergeo's service-role checks against the current hosted
-- Supabase/PostgREST claim contract (same defect class as
-- 20260829120000_bump_rate_counter_service_role_auth_role.sql).
--
-- Production (2026-11-26): every POST /ask fell back to search results with
-- notice ai.fallback.aiUnavailable. The API log shows
--   rpc/reserve_ask_quota_daily -> HTTP 400
--   "reserve_ask_quota_daily requires service role"
-- for a call made with the genuine service-role key. These functions read the
-- JWT role through the legacy flattened GUC
-- current_setting('request.jwt.claim.role', true), which the hosted platform
-- no longer populates (claims now live in the JSON GUC request.jwt.claims,
-- read by auth.role()). So the check rejected every caller, including
-- service_role, and Ask Vergeo never reached the model.
--
-- Fix: in each affected function, replace the legacy GUC read with
-- auth.role(). The trusted direct-session bypass
-- (session_user in ('postgres','supabase_admin')) and all other logic are
-- unchanged. anon/authenticated stay rejected: auth.role() returns 'anon' /
-- 'authenticated' for them, never 'service_role'.
--
-- The rewrite is done from each function's live definition so that no other
-- byte of the function body changes. It fails loudly if a listed function is
-- missing or still contains the legacy GUC afterwards.
--
-- Not reversed: restoring the old check would re-break Ask Vergeo on hosted
-- Supabase. The previous bodies are in 0024_ask_usage.sql and
-- 20261109120000_ask_vergeo_daily_quota.sql if ever needed.

do $$
declare
  fn record;
  def text;
  legacy constant text := 'current_setting(''request.jwt.claim.role'', true)';
  names constant text[] := array[
    'ask_quota_status',
    'reserve_ask_quota',
    'reserve_ask_quota_daily',
    'finalize_ask_answer',
    'release_ask_reservation',
    'reset_ask_kill_switch',
    'guard_ask_usage_mutation',
    'guard_ask_spend_monthly_mutation'
  ];
  seen integer := 0;
begin
  for fn in
    select p.oid, p.proname
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = any (names)
  loop
    def := pg_get_functiondef(fn.oid);
    if position(legacy in def) > 0 then
      execute replace(def, legacy, 'auth.role()');
    end if;
    seen := seen + 1;
  end loop;

  if seen < array_length(names, 1) then
    raise exception 'ask service-role fix: expected % functions, found %',
      array_length(names, 1), seen;
  end if;

  if exists (
    select 1
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = any (names)
      and position(legacy in p.prosrc) > 0
  ) then
    raise exception 'ask service-role fix: legacy request.jwt.claim.role read remains';
  end if;
end;
$$;
