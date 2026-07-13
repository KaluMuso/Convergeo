-- Follow-up to 0024, flagged by the Supabase security advisor (security_definer_view):
-- public.ask_usage_monthly was created without security_invoker, so it read
-- ask_usage with the view owner's privileges — any authenticated user granted
-- SELECT on the view could read the monthly aggregates regardless of the
-- admin-only RLS on the base table. Aggregate-only exposure (no PII), but the
-- intended posture is admin/service reads only.
--
-- security_invoker makes the view run with the caller's privileges, so the
-- ask_usage admin-only SELECT policy governs reads through the view: non-admin
-- authenticated callers now get zero rows; admins and service_role (BYPASSRLS)
-- are unaffected. No column/type change (packages/types unaffected).
--
-- Down (manual):
--   alter view public.ask_usage_monthly set (security_invoker = false);

alter view public.ask_usage_monthly set (security_invoker = true);
