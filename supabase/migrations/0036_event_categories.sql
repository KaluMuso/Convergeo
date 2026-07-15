-- D2: promote event category + landmark out of the HTML comment in
-- events.description into real, indexed columns backed by a taxonomy table.
--
-- Before: organiser_events.py serialised {category, landmark} into
-- <!--vergeo5:event-meta:{...}--> appended to events.description and parsed it
-- back at runtime. Consequences:
--   * category was neither indexed nor constrained;
--   * events_public browse/detail hardcoded category=None and never read the
--     meta, so filtering by any non-free category returned NOTHING;
--   * landmark lived outside the geo/data model;
--   * adding categories required code + redeploy, not data.
--
-- Additive + reversible. Down:
--   alter table public.events drop column category_slug, drop column landmark;
--   drop table public.event_categories;

create table public.event_categories (
  slug text primary key,
  parent_slug text references public.event_categories (slug) on delete restrict,
  label_key text not null,
  sort int not null default 0,
  created_at timestamptz not null default timezone('utc', now())
);

comment on table public.event_categories is
  'Extensible event category taxonomy (data-configurable). Seeded with the six '
  'Phase-1 launch categories; parent_slug allows future subcategory nesting '
  'toward the strategy''s ~11 top-level / ~65 subcategory catalogue.';

insert into public.event_categories (slug, label_key, sort) values
  ('workshops', 'events.categories.workshops', 10),
  ('comedy-theatre', 'events.categories.comedy_theatre', 20),
  ('pop-up-dinners', 'events.categories.pop_up_dinners', 30),
  ('cultural-arts', 'events.categories.cultural_arts', 40),
  ('lifestyle-community', 'events.categories.lifestyle_community', 50),
  ('free-rsvp', 'events.categories.free_rsvp', 60);

alter table public.events
  add column category_slug text references public.event_categories (slug) on delete restrict;

alter table public.events
  add column landmark text;

create index events_category_slug_idx on public.events (category_slug);

comment on column public.events.category_slug is
  'FK to event_categories. Replaces the category value formerly encoded in the '
  'events.description HTML meta comment.';
comment on column public.events.landmark is
  'Event-specific landmark (Zambia landmark+GPS addressing). Replaces the '
  'landmark value formerly encoded in the events.description HTML meta comment.';

-- Backfill category_slug + landmark from the legacy meta comment, then strip the
-- comment from the visible description. Only a recognised category slug is kept
-- (else NULL) so the FK never rejects a stray value.
update public.events e
set
  category_slug = case
    when (m.meta ->> 'category') in (select slug from public.event_categories)
      then m.meta ->> 'category'
    else null
  end,
  landmark = nullif(btrim(coalesce(m.meta ->> 'landmark', '')), ''),
  description = nullif(
    btrim(regexp_replace(e.description, '\n?<!--vergeo5:event-meta:\{.*\}-->\s*$', '')),
    ''
  )
from (
  select
    id,
    (regexp_match(description, '<!--vergeo5:event-meta:(\{.*\})-->'))[1]::jsonb as meta
  from public.events
  where description like '%<!--vergeo5:event-meta:%'
) m
where e.id = m.id and m.meta is not null;

-- ---------------------------------------------------------------------------
-- Row level security (convention: RLS on every table). Taxonomy is public-read,
-- admin-managed.
-- ---------------------------------------------------------------------------

alter table public.event_categories enable row level security;
alter table public.event_categories force row level security;

create policy event_categories_public_read
  on public.event_categories
  for select
  using (true);

comment on policy event_categories_public_read on public.event_categories is
  'Anyone may read the event category taxonomy.';

create policy event_categories_admin_all
  on public.event_categories
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy event_categories_admin_all on public.event_categories is
  'Platform admins may manage the event category taxonomy.';

grant select on table public.event_categories to anon, authenticated, service_role;
grant insert, update, delete on table public.event_categories to service_role;
