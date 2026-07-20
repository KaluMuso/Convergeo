-- 0063: Revoke public/anon/authenticated EXECUTE on the review-reply column-guard
-- trigger functions.
--
-- 0061 created public.guard_review_reply_columns() and
-- public.guard_service_review_reply_columns() but — unlike the vendor/event/service
-- lifecycle guards in 0057/0058 — did not revoke EXECUTE from anon/authenticated.
-- These are trigger-only functions: callable via PostgREST RPC they merely error
-- (no trigger NEW/OLD context), so this is hygiene, not an exploitable hole. Bring
-- them in line with the 0057/0058 grant posture so the Supabase security advisor is
-- clean and no SECURITY DEFINER function is needlessly exposed on the API surface.
--
-- Additive + reversible.
-- Down (manual): grant execute on function public.guard_review_reply_columns() to authenticated;
--                grant execute on function public.guard_service_review_reply_columns() to authenticated;

revoke all on function public.guard_review_reply_columns() from public;
revoke execute on function public.guard_review_reply_columns() from public, anon, authenticated;
grant execute on function public.guard_review_reply_columns() to postgres, service_role;

revoke all on function public.guard_service_review_reply_columns() from public;
revoke execute on function public.guard_service_review_reply_columns() from public, anon, authenticated;
grant execute on function public.guard_service_review_reply_columns() to postgres, service_role;
