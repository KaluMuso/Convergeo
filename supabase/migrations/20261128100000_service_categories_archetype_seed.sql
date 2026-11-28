-- Seed the six archetype service verticals into the admin-controlled taxonomy.
--
-- Why: service archetypes (20261128090000) added the verticals lodging, property,
-- fitness, rentals, family-fun and staffing as code constants. Once the taxonomy is
-- admin-controlled (20261127130000) a vendor can only create a service in a published
-- service_categories row, so these slugs must exist there or the archetype flows would
-- reject them. Additive and idempotent; admins can unpublish or rename any row later.
--
-- Reversal:
--   delete from public.service_categories
--    where slug in ('lodging', 'property', 'fitness', 'rentals', 'family-fun', 'staffing')
--      and not exists (select 1 from public.services s where s.category = service_categories.slug);

insert into public.service_categories (slug, parent_slug, name, path, sort, status)
values
  ('lodging', null, 'Lodging & stays', 'lodging', 110, 'published'),
  ('property', null, 'Property', 'property', 120, 'published'),
  ('fitness', null, 'Fitness & wellness', 'fitness', 130, 'published'),
  ('rentals', null, 'Rentals', 'rentals', 140, 'published'),
  ('family-fun', null, 'Family fun', 'family-fun', 150, 'published'),
  ('staffing', null, 'Staffing & hire', 'staffing', 160, 'published')
on conflict (slug) do nothing;
