-- 0064_force_rls_unforced_tables.sql
-- Closes VC-P02 / FD-07 (decision D32, gate G0): four tables enabled RLS but never
-- FORCED it, so the table owner (and any owner-privileged connection) bypassed
-- policies. Every other RLS table in this schema is already FORCED (house style
-- since 0004/0007); this aligns the stragglers found by a full migration sweep:
--   - ticket_type_instances   (0048)
--   - ticket_type_price_tiers (0049)
--   - product_relations       (0052)
--   - translation_overrides   (0053) — additional find beyond the audit's three
-- service_role keeps BYPASSRLS, so API/service access is unchanged.
-- Reversible: alter table ... no force row level security.

-- Grant repair: 0052 created product_relations with a public-read policy but no
-- table grants, so the policy was dead letter for client roles (the PDP rail
-- reads via service_role, which is why the feature still worked). Mirror the
-- event_categories (0036) grant shape: public read, service-role-only writes.
grant select on table public.product_relations to anon, authenticated, service_role;

grant insert, update, delete on table public.product_relations to service_role;

alter table public.ticket_type_instances force row level security;

alter table public.ticket_type_price_tiers force row level security;

alter table public.product_relations force row level security;

alter table public.translation_overrides force row level security;
