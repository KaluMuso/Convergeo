-- R02-P16 follow-on — product_class A–E on vendor_listings.
--
-- Migration 0085 added fulfilment_mode, lead_time_days, and condition=used for
-- per-measure / made-to-order / evidence shapes. This migration adds the
-- strategy-brief discriminator so cart, catalog, and vendor flows can branch on
-- class without inferring from fulfilment_mode alone.
--
-- Additive: default A preserves every existing listing.

alter table public.vendor_listings
  add column if not exists product_class char(1) not null default 'A',
  add column if not exists vendor_capacity_per_week integer;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_product_class_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_product_class_check
      check (product_class in ('A', 'B', 'C', 'D', 'E'));
  end if;

  -- Class D (unique/used): condition must be used — never new or refurbished.
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_class_d_condition_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_class_d_condition_check
      check (product_class <> 'D' or condition = 'used');
  end if;

  -- Class E (made-to-order): must declare lead time and weekly capacity.
  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_class_e_fields_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_class_e_fields_check
      check (
        product_class <> 'E'
        or (
          fulfilment_mode = 'made_to_order'
          and lead_time_days is not null
          and lead_time_days between 1 and 365
          and vendor_capacity_per_week is not null
          and vendor_capacity_per_week between 1 and 9999
        )
      );
  end if;

  if not exists (select 1 from pg_constraint where conname = 'vendor_listings_capacity_only_class_e_check') then
    alter table public.vendor_listings
      add constraint vendor_listings_capacity_only_class_e_check
      check (product_class = 'E' or vendor_capacity_per_week is null);
  end if;
end
$$;

comment on column public.vendor_listings.product_class is
  'Strategy brief class A–E. D=unique/used (evidence required in API). E=made-to-order (capacity + lead time).';
comment on column public.vendor_listings.vendor_capacity_per_week is
  'Required for product_class E — max units the vendor can accept per ISO week.';
