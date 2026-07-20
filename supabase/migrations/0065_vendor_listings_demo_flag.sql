-- 0065_vendor_listings_demo_flag.sql
-- Closes VC-P06 / FD-04 (gate G11): mark demo-seeded listings server-side so the
-- API can exclude them from PUBLIC search/browse once `public_launch` flips ON.
-- During invite-only beta (`public_launch=false`) demo inventory stays visible
-- with the honest client-side label (CUST-HOME-01), so flipping the flag — not a
-- deploy — is what retires the demo catalogue from public surfaces.
--
-- Backfill mirrors the client marker (apps/customer …/_components/demo-listing.ts):
-- a listing is demo when any of its images carries the `demo/` Cloudinary seed
-- prefix. Future demo seeds must set vendor_listings.demo = true directly.
-- Reversible: drop index, drop column.

alter table public.vendor_listings
  add column demo boolean not null default false;

update public.vendor_listings vl
set demo = true
where exists (
  select 1
  from public.listing_images li
  where li.listing_id = vl.id
    and (
      lower(li.cloudinary_public_id) like 'demo/%'
      or lower(li.cloudinary_public_id) like '%/demo/%'
    )
);

create index vendor_listings_demo_idx
  on public.vendor_listings (demo)
  where demo;
