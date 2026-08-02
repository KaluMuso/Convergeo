-- R02-P16 — product classes: per-measure, made-to-order, condition evidence.
--
-- A listing today is implicitly "one discrete new-or-refurbished unit":
-- `condition` is new|refurbished (0003) and price is per unit. Zambian retail
-- is not only that shape. Cloth, cable, timber, sand, maize and paint sell PER
-- MEASURE; furniture, tailoring and signage are MADE TO ORDER; and a large
-- second-hand market needs evidence, not adjectives.
--
-- MONEY RULE, and the reason this migration is shaped the way it is: money is
-- integer ngwee, and `Decimal` appears only at the Lenco boundary. Per-measure
-- pricing is exactly where a float tries hardest to creep in — "2.5 metres ×
-- K37.50" is the archetypal case.
--
-- So quantity is NOT a decimal. A listing declares the smallest sellable
-- increment (`unit_step_milli`, in thousandths of the sale unit, an integer),
-- and an order line carries an INTEGER COUNT OF STEPS. 2.5 m at a 0.5 m step
-- is 5 steps, and the line total is `steps × price_per_step_ngwee` — integer
-- multiplication with no rounding decision anywhere. Display converts steps to
-- human units at the very edge, through i18n number formatting.
--
-- Additive: every column is nullable or defaults to today's behaviour, so all
-- 134 existing listings keep working untouched.

alter table public.vendor_listings
  -- 'each' reproduces exactly what exists today.
  add column if not exists sale_unit text not null default 'each',
  -- Thousandths of the sale unit. 500 == half a metre; 1000 == one unit.
  -- Integer, so the smallest sellable amount is exact rather than a float that
  -- happens to look like 0.5.
  add column if not exists unit_step_milli integer not null default 1000,
  add column if not exists min_steps integer not null default 1,
  add column if not exists fulfilment_mode text not null default 'stocked',
  add column if not exists lead_time_days integer;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_sale_unit_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_sale_unit_check
      check (sale_unit in ('each', 'metre', 'kg', 'litre', 'bag', 'sqm'));
  end if;

  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_unit_step_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_unit_step_check
      check (unit_step_milli > 0 and min_steps > 0);
  end if;

  -- A discrete item cannot be sold in fractions: 'each' is pinned to whole
  -- units, so nobody can list half a phone by setting a 500 step.
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_each_is_whole_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_each_is_whole_check
      check (sale_unit <> 'each' or unit_step_milli = 1000);
  end if;

  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_fulfilment_mode_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_fulfilment_mode_check
      check (fulfilment_mode in ('stocked', 'made_to_order'));
  end if;

  -- Made-to-order without a lead time is a promise with no date on it. The
  -- customer is agreeing to wait, so they must be told how long.
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_lead_time_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_lead_time_check
      check (
        (fulfilment_mode = 'made_to_order' and lead_time_days is not null and lead_time_days between 1 and 365)
        or (fulfilment_mode = 'stocked' and lead_time_days is null)
      );
  end if;
end
$$;

comment on column public.vendor_listings.unit_step_milli is
  'Smallest sellable increment in thousandths of sale_unit (500 = half a metre). Integer by design: order lines carry a COUNT OF STEPS, never a decimal quantity, so no float ever touches a money path.';
comment on column public.vendor_listings.lead_time_days is
  'Required for made_to_order, forbidden for stocked. A made-to-order promise without a date is not a promise.';

-- ---------------------------------------------------------------------------
-- Condition evidence: widen the enum to include `used`.
-- ---------------------------------------------------------------------------
-- Widening a CHECK is additive in effect — every existing row stays legal and
-- no backfill is needed.
alter table public.vendor_listings
  drop constraint if exists vendor_listings_condition_check;

alter table public.vendor_listings
  add constraint vendor_listings_condition_check
  check (condition in ('new', 'refurbished', 'used'));

alter table public.vendor_listings
  add column if not exists defect_notes text;

-- A `used` item must carry a defect note. "Used" without a description is the
-- listing equivalent of a shrug, and disputes over second-hand goods are
-- exactly where escrow gets tested.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_used_needs_notes_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_used_needs_notes_check
      check (
        condition <> 'used'
        or (defect_notes is not null and char_length(btrim(defect_notes)) >= 10)
      );
  end if;
end
$$;

comment on column public.vendor_listings.defect_notes is
  'Required for condition = used (>=10 chars). Photographic evidence is enforced in the API against listing_images, which this table cannot see.';

-- ---------------------------------------------------------------------------
-- Line total: the only place step arithmetic should happen.
-- ---------------------------------------------------------------------------
create or replace function public.listing_line_total_ngwee(
  p_price_per_step_ngwee bigint,
  p_steps integer
)
returns bigint
language sql
immutable
as $$
  select p_price_per_step_ngwee * p_steps;
$$;

comment on function public.listing_line_total_ngwee(bigint, integer) is
  'Integer multiplication only. Exists so the step arithmetic has one home and cannot be re-derived with a float somewhere else.';
