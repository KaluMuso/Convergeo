-- Event archetypes: presentation templates (concert, religious, sports_family,
-- restaurant, private_gathering, generic) and their optional content.
--
-- Design: docs/plan/event-type-templates.md. Additive only:
--   * events.archetype         NULL = derived from category_slug by the API;
--                              a value is an organiser override;
--   * events.archetype_details validated JSON object (Pydantic per archetype in the API);
--   * events.sponsor_review_pending true while any sponsor inside archetype_details is
--     'pending' admin approval (maintained by the API; drives the admin review queue).
-- Presentation only: no payment, hold, ticket, fee or escrow object is touched.
-- Existing RLS on public.events covers the new columns (no new policy needed).
--
-- Down (reversible):
--   drop index if exists public.events_sponsor_review_pending_idx;
--   drop index if exists public.events_archetype_idx;
--   alter table public.events drop column if exists sponsor_review_pending,
--                             drop column if exists archetype_details,
--                             drop column if exists archetype;

alter table public.events
  add column if not exists archetype text
    check (
      archetype is null
      or archetype in (
        'concert', 'religious', 'sports_family', 'restaurant',
        'private_gathering', 'generic'
      )
    ),
  add column if not exists archetype_details jsonb not null default '{}'::jsonb
    check (
      jsonb_typeof(archetype_details) = 'object'
      and pg_column_size(archetype_details) <= 16384
    );

alter table public.events
  add column if not exists sponsor_review_pending boolean not null default false;

create index if not exists events_sponsor_review_pending_idx
  on public.events (sponsor_review_pending)
  where sponsor_review_pending;

create index if not exists events_archetype_idx
  on public.events (archetype)
  where archetype is not null;

comment on column public.events.archetype is
  'Presentation archetype override. NULL = derived from category_slug by the API.';
comment on column public.events.sponsor_review_pending is
  'True while a sponsor in archetype_details awaits admin approval; set by the API.';
comment on column public.events.archetype_details is
  'Per-archetype optional content (lineup, agenda, sponsors, menu...). Validated by the API; readers must tolerate junk.';
