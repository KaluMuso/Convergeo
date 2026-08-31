-- Fix cleanup_expired_rate_counters()'s service-role check against the same
-- hosted Supabase/PostgREST claim contract 20260829120000 fixed for
-- bump_rate_counter() and 20260831050000 fixed for
-- guard_rate_counters_mutation().
--
-- Live staging DB inspection found this third sibling function still reading
-- the legacy flattened GUC `request.jwt.claim.role`, which the current
-- hosted platform no longer populates — rejecting a genuine service-role
-- caller (e.g. the scheduled n8n/cron cleanup this function's own comment
-- says it is for) exactly like the other two did before their fixes. Not
-- proven live-broken via a direct HTTP call in this task (never invoked
-- destructively against hosted staging here), but it is the identical
-- pattern, on the same table, in the same migration file, so left unfixed it
-- would immediately reproduce the same class of failure the moment
-- something actually calls it.
--
-- Fix: switch the JWT-role comparison to auth.role(), matching the other two
-- fixes exactly. session_user trusted-bypass, SECURITY DEFINER, search_path,
-- delete logic, and error message are otherwise byte-for-byte unchanged from
-- 0011_rate_counters.sql.
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
     and coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'cleanup_expired_rate_counters requires service role';
  end if;

  delete from public.rate_counters
  where expires_at < now();

  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

comment on function public.cleanup_expired_rate_counters() is
  'Deletes expired rate counter rows; intended for scheduled n8n/cron '
  'cleanup. Service-role check uses auth.role() (the current hosted '
  'PostgREST/GoTrue claim contract), matching bump_rate_counter() and '
  'guard_rate_counters_mutation().';
