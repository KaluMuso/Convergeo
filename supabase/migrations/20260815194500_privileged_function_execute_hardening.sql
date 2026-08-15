-- SEC-DB-01: Revoke overbroad EXECUTE on internal SECURITY DEFINER functions.
--
-- Supabase Security Advisor flags SECURITY DEFINER functions callable by anon or
-- authenticated via PostgREST. Trigger guards and backend-only RPCs must not be
-- client-invokable; triggers still fire without caller EXECUTE.
--
-- Complements 0050 (pre-0072 sweep) and 20260813160200 (has_role / search RPCs).
-- Idempotent: safe to re-apply after CREATE OR REPLACE that resets PUBLIC grants.
--
-- Intentionally NOT revoked (documented public RPCs):
--   * public.has_role(text) — SECURITY INVOKER delegator for RLS (60200)
--   * public.vendor_licence_is_valid(uuid, text) — boolean badge only (0084)
--   * public.vendor_follower_count(uuid) — authenticated vendor metric (0083)
--   * public.product_class_customer_released(char) — flag-gated discovery (64106)

-- ---------------------------------------------------------------------------
-- Trigger guards added after 0050 without explicit EXECUTE hygiene
-- ---------------------------------------------------------------------------
revoke all on function public.clip_products_guard() from public;
revoke execute on function public.clip_products_guard() from public, anon, authenticated;
grant execute on function public.clip_products_guard() to postgres, service_role;

revoke all on function public.enquiry_threads_guard() from public;
revoke execute on function public.enquiry_threads_guard() from public, anon, authenticated;
grant execute on function public.enquiry_threads_guard() to postgres, service_role;

revoke all on function public.listing_location_stock_guard() from public;
revoke execute on function public.listing_location_stock_guard() from public, anon, authenticated;
grant execute on function public.listing_location_stock_guard() to postgres, service_role;

revoke all on function public.rfq_threads_guard() from public;
revoke execute on function public.rfq_threads_guard() from public, anon, authenticated;
grant execute on function public.rfq_threads_guard() to postgres, service_role;

revoke all on function public.storefront_collection_items_guard() from public;
revoke execute on function public.storefront_collection_items_guard() from public, anon, authenticated;
grant execute on function public.storefront_collection_items_guard() to postgres, service_role;

revoke all on function public.guard_vendor_licence_status_update() from public;
revoke execute on function public.guard_vendor_licence_status_update() from public, anon, authenticated;
grant execute on function public.guard_vendor_licence_status_update() to postgres, service_role;

-- ---------------------------------------------------------------------------
-- Backend-only RPCs — re-assert service_role after rehearsal CREATE OR REPLACE
-- ---------------------------------------------------------------------------
revoke all on function public.clip_bump_counter(uuid, text, integer) from public;
revoke execute on function public.clip_bump_counter(uuid, text, integer)
  from public, anon, authenticated;
grant execute on function public.clip_bump_counter(uuid, text, integer) to service_role;

revoke all on function public.clip_record_spend(text, bigint, integer, bigint, bigint)
  from public;
revoke execute on function public.clip_record_spend(text, bigint, integer, bigint, bigint)
  from public, anon, authenticated;
grant execute on function public.clip_record_spend(text, bigint, integer, bigint, bigint)
  to service_role;

revoke all on function public.reset_clip_kill_switch(text) from public;
revoke execute on function public.reset_clip_kill_switch(text)
  from public, anon, authenticated;
grant execute on function public.reset_clip_kill_switch(text) to service_role;

-- ---------------------------------------------------------------------------
-- Advisor: mutable search_path on immutable helper (not SECURITY DEFINER)
-- ---------------------------------------------------------------------------
alter function public.listing_line_total_ngwee(bigint, integer)
  set search_path = public;
