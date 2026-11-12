-- Vendor brand theme (storefront-only colours).
--
-- Vendors may set a primary + accent colour that re-skins THEIR storefront page
-- only. The API clamps both to WCAG AA before storing (primary: white text
-- >= 4.5:1; accent >= 3:1 on white); this constraint guards the shape so a
-- direct write can never store anything but `{ "primary": "#RRGGBB" | null,
-- "accent": "#RRGGBB" | null }`.
--
-- Additive, nullable (safe after M03). Inherits the vendors table RLS — owner
-- writes through the API (service role), public reads via the directory
-- endpoint, exactly like logo_url / cover_url. No policy change.
--
-- Reversible:
--   alter table public.vendors drop constraint if exists vendors_brand_theme_shape;
--   alter table public.vendors drop column if exists brand_theme;

alter table public.vendors
  add column if not exists brand_theme jsonb;

alter table public.vendors
  drop constraint if exists vendors_brand_theme_shape;

alter table public.vendors
  add constraint vendors_brand_theme_shape check (
    brand_theme is null
    or (
      jsonb_typeof(brand_theme) = 'object'
      and (brand_theme - 'primary' - 'accent') = '{}'::jsonb
      and (
        not (brand_theme ? 'primary')
        or brand_theme->'primary' = 'null'::jsonb
        or (brand_theme->>'primary') ~ '^#[0-9A-Fa-f]{6}$'
      )
      and (
        not (brand_theme ? 'accent')
        or brand_theme->'accent' = 'null'::jsonb
        or (brand_theme->>'accent') ~ '^#[0-9A-Fa-f]{6}$'
      )
    )
  );

comment on column public.vendors.brand_theme is
  'Storefront-only brand colours {primary, accent} as #RRGGBB (AA-clamped by the API). NULL = platform palette.';
