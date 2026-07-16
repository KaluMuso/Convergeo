-- 0044: Add a canonical long-form description to products.
--
-- (Renumbered 0041 → 0044: four migrations merged in parallel racing on two slots —
--  0041 (event_classification + this) and 0042 (ticket_attendee_names + vendor_whatsapp)
--  — duplicate version prefixes that break `supabase db start` (schema_migrations PK,
--  SQLSTATE 23505) and redden the db/rls CI jobs on master. 0043 was then taken by
--  0043_harden_function_search_path, so this independent product migration moves to the
--  next free slot; body unchanged.)
--
-- The PDP shows a "Specifications" table (products.spec, jsonb) and reviews, but
-- there was no place to hold the human-readable product description the storefront
-- design calls for (the "Overview" / "Description" tab). Vendor listings carry a
-- title override only; the canonical product had name + brand + spec and nothing
-- prose. This adds that field so the PDP can render an Overview tab and richer
-- product JSON-LD / meta descriptions later.
--
-- Scope mirrors `spec`: this is CANONICAL catalog data (one row per canonical
-- product), populated by catalog/seed tooling — not a per-vendor or CRUD-form
-- field, so no write endpoint changes here. Read path only (products router).
--
-- Additive, nullable column (safe after M03). Existing rows stay NULL and the PDP
-- omits the Overview tab until a description is set. Inherits the products table's
-- existing RLS policies — no policy change needed.
--
-- Reversible: `alter table public.products drop column description;`

alter table public.products
  add column if not exists description text;

comment on column public.products.description is
  'Canonical long-form product description (Overview tab / meta). NULL until set by catalog tooling. Mirrors spec: not a per-vendor field.';
