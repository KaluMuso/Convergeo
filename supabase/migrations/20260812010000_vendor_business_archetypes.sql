-- Strategy alignment: preserve the seller's operating model separately from
-- the merchandise category already stored in vendors.archetype.
--
-- The strategy defines six operating archetypes that drive onboarding,
-- education, fulfilment guidance, and workbench defaults. The existing
-- vendors.archetype column contains product verticals (electronics, groceries,
-- and so on), so overloading it loses an important business dimension.

alter table public.vendors
  add column if not exists business_archetype text;

alter table public.vendors
  drop constraint if exists vendors_business_archetype_check;

alter table public.vendors
  add constraint vendors_business_archetype_check
  check (
    business_archetype is null
    or business_archetype in (
      'market_trader',
      'registered_retailer',
      'service_professional',
      'manufacturer',
      'importer_wholesaler',
      'event_organiser'
    )
  );

comment on column public.vendors.business_archetype is
  'Strategy operating archetype, distinct from the seller merchandise category in vendors.archetype.';
