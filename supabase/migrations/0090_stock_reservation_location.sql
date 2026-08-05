-- R02-P08 follow-on — persist branch context on cart lines and stock reservations.
--
-- Cart lines carry the customer's chosen (or delivery-nearest) branch so add-to-cart
-- validation and checkout claims gate on the same location_id. Reservations store
-- location_id so timeout release restocks the correct branch row.

alter table public.cart_items
  add column if not exists pickup_location_id uuid
    references public.vendor_locations (id) on delete set null;

comment on column public.cart_items.pickup_location_id is
  'Branch selected for stock validation/claim (pickup choice or delivery-nearest). Nullable for legacy pooled listings.';

create index if not exists cart_items_pickup_location_id_idx
  on public.cart_items (pickup_location_id)
  where pickup_location_id is not null;

alter table public.stock_reservations
  add column if not exists location_id uuid
    references public.vendor_locations (id) on delete set null;

comment on column public.stock_reservations.location_id is
  'Branch whose listing_location_stock row was decremented at claim; NULL for legacy pooled vendor_listings.stock_qty claims.';

create index if not exists stock_reservations_location_id_idx
  on public.stock_reservations (location_id)
  where location_id is not null;
