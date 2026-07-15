-- FIX (strategy alignment): persist the vendor business archetype chosen at onboarding.
--
-- Previously the onboarding "business category" (see apps/vendor .../onboarding/_lib)
-- lived ONLY in the browser localStorage draft and was dropped on KYC submit — the
-- backend kept no record of the vendor's archetype, so nothing could drive the
-- archetype-tailored vendor experience the business-pipeline strategy describes.
--
-- Additive, nullable column (safe after M03). Existing vendor rows stay NULL until
-- the owner (re)submits KYC or an admin backfills. Values mirror the onboarding
-- BUSINESS_CATEGORIES set; the CHECK keeps them constrained without a lookup table.

alter table public.vendors
  add column if not exists archetype text;

alter table public.vendors
  drop constraint if exists vendors_archetype_check;

alter table public.vendors
  add constraint vendors_archetype_check
  check (
    archetype is null
    or archetype in (
      'electronics',
      'home',
      'fashion_beauty',
      'services',
      'groceries',
      'other'
    )
  );

comment on column public.vendors.archetype is
  'Vendor business archetype/category selected at onboarding, persisted from KYC submit. NULL until set.';
