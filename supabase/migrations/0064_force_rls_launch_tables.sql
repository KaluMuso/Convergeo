-- 0064: FORCE ROW LEVEL SECURITY on D32 / G0 launch tables that already had
-- ENABLE RLS but not FORCE (table-owner sessions could otherwise bypass policies).
--
-- Targets (D32): ticket_type_instances, ticket_type_price_tiers, product_relations.
-- Existing policies and grants are preserved unchanged — no new client access.
--
-- Idempotent: ENABLE/FORCE are safe to re-run.
-- Reversible:
--   alter table public.ticket_type_instances no force row level security;
--   alter table public.ticket_type_price_tiers no force row level security;
--   alter table public.product_relations no force row level security;

alter table public.ticket_type_instances enable row level security;
alter table public.ticket_type_instances force row level security;

alter table public.ticket_type_price_tiers enable row level security;
alter table public.ticket_type_price_tiers force row level security;

alter table public.product_relations enable row level security;
alter table public.product_relations force row level security;
