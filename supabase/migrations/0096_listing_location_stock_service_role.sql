-- STG-SEED-HOTFIX-07: service_role writes branch stock (seed + claim/release path).
-- Migration 0081 documented service-role-only mutations but omitted the table grant.

grant insert, update, delete on public.listing_location_stock to service_role;
