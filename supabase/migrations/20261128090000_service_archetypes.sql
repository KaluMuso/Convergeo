-- Service archetypes: per-service template override + validated attribute blobs.
--
-- Design: docs/plan/service-type-templates.md. Additive only:
--   * services.archetype      nullable override (null = derived from the vertical);
--   * services.attributes     service-level attributes (amenities, hours, schedule, ...);
--   * service_packages.attributes  archetype-specific offer attributes.
-- Shapes are validated by the API (Pydantic, one model per archetype); the database only
-- bounds the value (an object, <= 8000 bytes) so a bad writer cannot store a huge blob.
-- Gallery reuses services.portfolio_images. No money, order or payment object is touched.
-- New verticals (lodging, property, fitness, rentals, family-fun, staffing) need no schema
-- change: services.category is free text.
--
-- Down (reversible):
--   alter table public.service_packages drop constraint if exists service_packages_attributes_check;
--   alter table public.service_packages drop column if exists attributes;
--   alter table public.services drop constraint if exists services_attributes_check;
--   alter table public.services drop constraint if exists services_archetype_check;
--   alter table public.services drop column if exists attributes, drop column if exists archetype;

alter table public.services
  add column if not exists archetype text,
  add column if not exists attributes jsonb not null default '{}'::jsonb;

alter table public.services
  add constraint services_archetype_check
    check (
      archetype is null
      or archetype in (
        'accommodation', 'appointment', 'membership', 'on_site',
        'rental', 'ticketed', 'professional'
      )
    ),
  add constraint services_attributes_check
    check (jsonb_typeof(attributes) = 'object' and octet_length(attributes::text) <= 8000);

alter table public.service_packages
  add column if not exists attributes jsonb not null default '{}'::jsonb;

alter table public.service_packages
  add constraint service_packages_attributes_check
    check (jsonb_typeof(attributes) = 'object' and octet_length(attributes::text) <= 8000);

comment on column public.services.archetype is
  'Template override (accommodation|appointment|membership|on_site|rental|ticketed|professional); null = derived from category. Unrelated to vendors.archetype.';
comment on column public.services.attributes is
  'Service-level attributes validated per archetype by the API (amenities, hours, policy, schedule, staff).';
comment on column public.service_packages.attributes is
  'Archetype-specific offer attributes (room type, duration, pass kind, deposit, ...) validated by the API.';
