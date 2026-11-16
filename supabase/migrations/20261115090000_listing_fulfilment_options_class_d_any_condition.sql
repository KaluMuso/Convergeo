-- Vendor-portal QA W2: (1) Class D may be new/refurbished/used, (2) per-listing
-- fulfilment options.
--
-- 1. Class D is "one-of-a-kind / unique". 0087 forced condition = 'used', which
--    made a brand-new one-off item (a handmade T-shirt) unlistable. Used stock
--    keeps its own duties (defect notes >= 10 chars, photo evidence before
--    activation) via vendor_listings_used_needs_notes_check and the evidence
--    triggers, so only the Class D coupling is relaxed. Widening a CHECK is
--    additive in effect: every existing row stays legal.
--
-- 2. fulfilment_options records which hand-over routes a vendor offers for a
--    listing. Default {lusaka_delivery,pickup_shop} is exactly what checkout
--    offered for every listing before this migration, so no behaviour changes
--    for existing rows.
--      lusaka_delivery    vendor/platform delivery inside Lusaka zones
--      pickup_shop        customer collects at the shop or a branch
--      pickup_nationwide  collection arranged for buyers anywhere in Zambia
--
-- Reversible rollback:
--   ALTER TABLE public.vendor_listings DROP CONSTRAINT IF EXISTS vendor_listings_fulfilment_options_check;
--   ALTER TABLE public.vendor_listings DROP COLUMN IF EXISTS fulfilment_options;
--   -- Re-adding the Class D constraint requires first fixing any new/refurbished
--   -- Class D rows created after this migration:
--   -- ALTER TABLE public.vendor_listings ADD CONSTRAINT vendor_listings_class_d_condition_check
--   --   CHECK (product_class <> 'D' OR condition = 'used');

alter table public.vendor_listings
  drop constraint if exists vendor_listings_class_d_condition_check;

alter table public.vendor_listings
  add column if not exists fulfilment_options text[] not null
    default array['lusaka_delivery', 'pickup_shop']::text[];

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'vendor_listings_fulfilment_options_check'
  ) then
    alter table public.vendor_listings
      add constraint vendor_listings_fulfilment_options_check
      check (
        cardinality(fulfilment_options) between 1 and 3
        and fulfilment_options <@ array['lusaka_delivery', 'pickup_shop', 'pickup_nationwide']::text[]
      );
  end if;
end
$$;

comment on column public.vendor_listings.fulfilment_options is
  'Hand-over routes the vendor offers for this listing: lusaka_delivery, pickup_shop, pickup_nationwide. Checkout only offers routes every line in a vendor group allows.';
