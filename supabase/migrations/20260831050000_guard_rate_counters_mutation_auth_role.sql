-- Fix guard_rate_counters_mutation()'s service-role check against the same
-- hosted Supabase/PostgREST claim contract 20260829120000 already fixed for
-- bump_rate_counter().
--
-- 20260829120000 switched bump_rate_counter()'s own outer guard to
-- auth.role(), which made GET /discovery/home's underlying
-- POST /rest/v1/rpc/bump_rate_counter call pass that check. Live staging
-- inspection after that fix still showed GET /discovery/home returning
-- HTTP 500, now traced to the RPC itself failing with HTTP 400
-- "rate_counters is service-role only" — a different message than before,
-- proving the request now clears bump_rate_counter's own check and instead
-- fails inside its INSERT/UPDATE against public.rate_counters, which fires
-- the BEFORE trigger rate_counters_guard_mutation calling
-- guard_rate_counters_mutation(). That function's body still reads the
-- legacy flattened GUC `current_setting('request.jwt.claim.role', true)`,
-- which the current hosted platform no longer populates — the exact
-- split-brain defect 20260829120000 fixed in bump_rate_counter() itself,
-- left behind in this sibling guard.
--
-- Fix: switch the JWT-role comparison to auth.role(), matching
-- 20260829120000 and the session_user bypass convention already used by
-- 0057/0058's client guards. Error message and control flow are otherwise
-- byte-for-byte unchanged from 0011_rate_counters.sql — anon and
-- authenticated remain rejected (auth.role() returns 'anon' /
-- 'authenticated' for them, never 'service_role'); no client mutation
-- grants are added.
create or replace function public.guard_rate_counters_mutation()
returns trigger
language plpgsql
as $$
begin
  if session_user in ('postgres', 'supabase_admin') then
    return coalesce(new, old);
  end if;

  if coalesce(auth.role(), '') = 'service_role' then
    return coalesce(new, old);
  end if;

  raise exception 'rate_counters is service-role only';
end;
$$;

comment on function public.guard_rate_counters_mutation() is
  'Row-mutation guard for public.rate_counters. Allows service_role '
  '(checked via auth.role(), the current hosted PostgREST/GoTrue claim '
  'contract) or a trusted direct DB session (postgres/supabase_admin). '
  'anon/authenticated are rejected — no client mutation grants exist.';
