-- 0047: Pin a fixed search_path on functions flagged by the Supabase security
-- linter (`function_search_path_mutable`, lint 0011).
--
-- All eight functions are SECURITY INVOKER (they run with the caller's rights,
-- so this is hardening rather than a privilege-escalation fix), but a mutable
-- search_path still lets a caller shadow unqualified object references. Pinning
-- `public, extensions` resolves the lint and blocks shadowing while preserving
-- behaviour: every referenced object lives in `public`, and extension operators
-- (pg_trgm / vector) resolve from `extensions`. pg_catalog is always implicitly
-- first, so built-ins keep resolving.
--
-- Signatures are spelled out (none are overloaded) so the ALTERs are precise.
-- Reversible: `alter function ... reset search_path;` per function.

alter function public.ask_current_month_key() set search_path = public, extensions;
alter function public.cart_guest_token() set search_path = public, extensions;
alter function public.guard_ask_spend_monthly_mutation() set search_path = public, extensions;
alter function public.guard_ask_usage_mutation() set search_path = public, extensions;
alter function public.guard_rate_counters_mutation() set search_path = public, extensions;
alter function public.is_valid_price_tiers(tiers jsonb) set search_path = public, extensions;
alter function public.search_apply_boost(p_base_score double precision, p_boost_signals jsonb)
  set search_path = public, extensions;
alter function public.set_updated_at() set search_path = public, extensions;
