-- 0041: Add a canonical long-form description to products.
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
