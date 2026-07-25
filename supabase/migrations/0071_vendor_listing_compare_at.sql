-- Struck-price support (P1): optional "compare-at" (was) price on a vendor
-- listing. Additive, nullable; a set value must exceed the live price so the
-- displayed discount is always positive. The catalog serializer exposes it to
-- the customer as `oldNgwee`; the PLP renders a struck price + −% chip only
-- when it is present (the frontend shipped inert in #458).

alter table public.vendor_listings
  add column if not exists compare_at_ngwee bigint;

alter table public.vendor_listings
  drop constraint if exists vendor_listings_compare_at_gt_price;

alter table public.vendor_listings
  add constraint vendor_listings_compare_at_gt_price
  check (compare_at_ngwee is null or compare_at_ngwee > price_ngwee);

comment on column public.vendor_listings.compare_at_ngwee is
  'Optional compare-at/was price (integer ngwee). NULL = no discount. Must exceed price_ngwee so the discount is positive. Serialized to the customer as oldNgwee.';
