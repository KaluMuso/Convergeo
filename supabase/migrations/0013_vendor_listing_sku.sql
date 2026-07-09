-- 0013_vendor_listing_sku.sql
-- Additive (convention #6): per-vendor SKU on vendor_listings for bulk CSV import
-- idempotency (M12-P06 convergence). Prior to this the importer smuggled the SKU
-- into title_override as "sku:<sku>|<title>", which corrupted the customer-facing
-- display title (search projection, PDP, cart, checkout all read title_override).
-- Now the SKU has its own column and title_override holds the real title.
--
-- Reversible:
--   drop index if exists public.vendor_listings_vendor_sku_key;
--   alter table public.vendor_listings drop column if exists sku;

alter table public.vendor_listings
  add column if not exists sku text;

-- Idempotency key: a vendor cannot hold two listings with the same non-null SKU.
-- Partial (where sku is not null) so hand-created listings without a SKU are
-- unconstrained and multiple null SKUs per vendor remain allowed.
create unique index if not exists vendor_listings_vendor_sku_key
  on public.vendor_listings (vendor_id, sku)
  where sku is not null;

comment on column public.vendor_listings.sku is
  'Vendor-supplied stock keeping unit; unique per vendor when set. Drives CSV import idempotency (M12-P06).';
