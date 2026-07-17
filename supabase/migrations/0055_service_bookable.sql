-- 0055: Direct booking — bookable services with a fixed price.
--
-- Adds an opt-in "book now" path alongside RFQ. A vendor flips `bookable` on and
-- sets a fixed `booking_price_ngwee`; a customer then books at that price and the
-- existing RFQ money spine (accept_quote → deposit escrow → completion) runs
-- unchanged — a booking synthesizes a job + accepted quote at this fixed price.
-- Additive; reversible (drop constraint + columns).

alter table public.services
  add column if not exists bookable boolean not null default false;

alter table public.services
  add column if not exists booking_price_ngwee bigint;

-- A bookable service must carry a positive fixed price; non-bookable may leave it
-- null. Existing rows default bookable=false, so the check holds for all of them.
alter table public.services
  drop constraint if exists services_booking_price_check;
alter table public.services
  add constraint services_booking_price_check
  check (not bookable or (booking_price_ngwee is not null and booking_price_ngwee > 0));

comment on column public.services.bookable is
  'When true, customers can book this service directly at booking_price_ngwee (deposit escrow via the RFQ spine), alongside RFQ.';
comment on column public.services.booking_price_ngwee is
  'Fixed total price (integer ngwee) for a direct booking. Required (> 0) when bookable.';
