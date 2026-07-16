-- 0044: Vendor storefront cover image.
--
-- The public vendor page renders a gradient placeholder where a cover/banner
-- image should be ("no cover image in the vendor data model yet"). This adds the
-- column so a vendor can upload a banner (Cloudinary secure_url, same as
-- logo_url) that heads their storefront.
--
-- Additive, nullable (safe after M03). Existing rows stay NULL and the storefront
-- keeps the gradient placeholder until a cover is set. Inherits the vendors table
-- RLS — no policy change. Stored as a full Cloudinary secure URL, mirroring
-- logo_url.
--
-- Reversible: `alter table public.vendors drop column cover_url;`

alter table public.vendors
  add column if not exists cover_url text;

comment on column public.vendors.cover_url is
  'Vendor storefront cover/banner image (Cloudinary secure URL). NULL until set; storefront falls back to a gradient. Mirrors logo_url.';
