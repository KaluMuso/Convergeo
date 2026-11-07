-- The public PDP related-products endpoint reads curated relations with its
-- server-owned client. Browser roles retain their existing denial policies.
grant select on table public.product_relations to service_role;
