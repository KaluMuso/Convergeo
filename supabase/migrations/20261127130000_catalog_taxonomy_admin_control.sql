-- Admin-controlled catalog taxonomy: umbrella, publish/block status, imagery and
-- per-app visibility on the three existing taxonomy tables.
--
-- One logical taxonomy, three physical tables (kept on purpose so every existing
-- FK, slug and reader stays valid):
--   product + wholesale umbrellas -> public.categories          (umbrella column, new)
--   service umbrella              -> public.service_categories  (verticals + sub-categories)
--   event umbrella                -> public.event_categories    (events.category_slug FK target)
-- The admin API (services/api/app/services/categories/taxonomy.py) presents them as one
-- tree per umbrella; slugs and ids are NOT changed.
--
-- Additive + reversible. Existing rows keep behaving exactly as before: status defaults
-- to 'published' and both visibility flags default to true. One exception is documented
-- in section 4 (unwired service-catalogue seed rows start as 'draft').
--
-- Public read policy changes from `using (true)` to "published and visible in at least
-- one app"; blocked/draft rows are no longer readable with the anon/authenticated key.
-- Admin writes happen only through the API as service_role (D1, 20261115140100); the
-- legacy admin_all policies on event_categories/service_categories are dropped and
-- client write grants revoked.
--
-- Down (manual):
--   drop trigger if exists categories_guard_umbrella_parent on public.categories;
--   drop function if exists public.guard_category_umbrella_parent();
--   -- restore the previous public-read policies:
--   drop policy if exists categories_public_select on public.categories;
--   create policy categories_public_select on public.categories for select using (true);
--   drop policy if exists event_categories_public_read on public.event_categories;
--   create policy event_categories_public_read on public.event_categories for select using (true);
--   create policy event_categories_admin_all on public.event_categories for all to authenticated
--     using (public.has_role('admin')) with check (public.has_role('admin'));
--   drop policy if exists service_categories_public_read on public.service_categories;
--   create policy service_categories_public_read on public.service_categories for select using (true);
--   create policy service_categories_admin_all on public.service_categories for all to authenticated
--     using (public.has_role('admin')) with check (public.has_role('admin'));
--   delete from public.service_categories where slug in ('logistics-delivery', 'packaging-supplies');
--   alter table public.categories
--     drop constraint if exists categories_umbrella_product_or_wholesale,
--     drop constraint if exists categories_image_public_id_check,
--     drop constraint if exists categories_image_alt_check,
--     drop constraint if exists categories_icon_check,
--     drop column umbrella, drop column status, drop column image_public_id,
--     drop column image_alt, drop column icon, drop column show_in_customer,
--     drop column show_in_vendor, drop column updated_by;
--   alter table public.event_categories
--     drop constraint if exists event_categories_image_public_id_check,
--     drop constraint if exists event_categories_image_alt_check,
--     drop constraint if exists event_categories_icon_check,
--     drop constraint if exists event_categories_name_check,
--     drop trigger if exists event_categories_set_updated_at on public.event_categories;
--   alter table public.event_categories
--     drop column name, drop column status, drop column image_public_id, drop column image_alt,
--     drop column icon, drop column show_in_customer, drop column show_in_vendor,
--     drop column updated_at, drop column updated_by;
--   alter table public.service_categories
--     drop constraint if exists service_categories_image_public_id_check,
--     drop constraint if exists service_categories_image_alt_check,
--     drop constraint if exists service_categories_icon_check;
--   alter table public.service_categories
--     drop column status, drop column image_public_id, drop column image_alt, drop column icon,
--     drop column show_in_customer, drop column show_in_vendor, drop column updated_by;
--   drop type public.taxonomy_status;
--   drop type public.taxonomy_umbrella;

-- ---------------------------------------------------------------------------
-- 1. Enums
-- ---------------------------------------------------------------------------
create type public.taxonomy_umbrella as enum ('product', 'service', 'event', 'wholesale');
create type public.taxonomy_status as enum ('draft', 'published', 'blocked');

comment on type public.taxonomy_umbrella is
  'Top-level catalog area a taxonomy node belongs to (admin Categories tabs).';
comment on type public.taxonomy_status is
  'draft = not yet visible; published = visible per show_in_* flags; blocked = hidden from '
  'pickers/menus/pages but existing listings stay readable.';

-- ---------------------------------------------------------------------------
-- 2. categories (products + wholesale)
-- ---------------------------------------------------------------------------
alter table public.categories
  add column umbrella public.taxonomy_umbrella not null default 'product',
  add column status public.taxonomy_status not null default 'published',
  add column image_public_id text,
  add column image_alt text,
  add column icon text,
  add column show_in_customer boolean not null default true,
  add column show_in_vendor boolean not null default true,
  add column updated_by uuid;

alter table public.categories
  add constraint categories_umbrella_product_or_wholesale
    check (umbrella in ('product', 'wholesale')),
  add constraint categories_image_public_id_check
    check (image_public_id is null or (length(image_public_id) between 1 and 500
      and image_public_id !~ '\.\.' and image_public_id !~ '^/')),
  add constraint categories_image_alt_check
    check (image_alt is null or length(image_alt) <= 200),
  add constraint categories_icon_check
    check (icon is null or icon ~ '^[a-z0-9][a-z0-9-]{0,39}$');

create index categories_umbrella_status_idx on public.categories (umbrella, status);

comment on column public.categories.umbrella is
  'product (default, every existing row) or wholesale. Children must share the parent umbrella.';
comment on column public.categories.status is
  'draft | published | blocked. Blocked hides the node from customer/vendor pickers, menus '
  'and /c pages; existing listings keep working.';
comment on column public.categories.image_public_id is
  'Cloudinary public id of the category tile image (public media, f_auto/q_auto delivery).';
comment on column public.categories.position is
  'Sibling sort order (admin drag/arrow reorder writes this).';

create function public.guard_category_umbrella_parent()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  parent_umbrella public.taxonomy_umbrella;
begin
  if new.parent_id is null then
    return new;
  end if;
  select c.umbrella into parent_umbrella from public.categories c where c.id = new.parent_id;
  if parent_umbrella is not null and parent_umbrella <> new.umbrella then
    raise exception 'category umbrella must match its parent umbrella'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger categories_guard_umbrella_parent
  before insert or update of parent_id, umbrella on public.categories
  for each row
  execute function public.guard_category_umbrella_parent();

-- ---------------------------------------------------------------------------
-- 3. event_categories
-- ---------------------------------------------------------------------------
alter table public.event_categories
  add column name text,
  add column status public.taxonomy_status not null default 'published',
  add column image_public_id text,
  add column image_alt text,
  add column icon text,
  add column show_in_customer boolean not null default true,
  add column show_in_vendor boolean not null default true,
  add column updated_at timestamptz not null default timezone('utc', now()),
  add column updated_by uuid;

alter table public.event_categories
  add constraint event_categories_name_check
    check (name is null or length(btrim(name)) between 1 and 120),
  add constraint event_categories_image_public_id_check
    check (image_public_id is null or (length(image_public_id) between 1 and 500
      and image_public_id !~ '\.\.' and image_public_id !~ '^/')),
  add constraint event_categories_image_alt_check
    check (image_alt is null or length(image_alt) <= 200),
  add constraint event_categories_icon_check
    check (icon is null or icon ~ '^[a-z0-9][a-z0-9-]{0,39}$');

create trigger event_categories_set_updated_at
  before update on public.event_categories
  for each row
  execute function public.set_updated_at();

comment on column public.event_categories.name is
  'Display name for admin-created categories and fallback when no i18n label exists for '
  'label_key. Seeded launch categories keep resolving through label_key.';

-- English display names for every seeded row (fallback / admin tree labels).
update public.event_categories set name = v.name
from (values
  ('workshops', 'Workshops'),
  ('comedy-theatre', 'Comedy & theatre'),
  ('pop-up-dinners', 'Pop-up dinners'),
  ('cultural-arts', 'Cultural & arts'),
  ('lifestyle-community', 'Lifestyle & community'),
  ('free-rsvp', 'Free RSVP'),
  ('music', 'Music'),
  ('comedy-theatre-parent', 'Comedy & theatre'),
  ('sports', 'Sports'),
  ('conferences-workshops', 'Conferences & workshops'),
  ('family', 'Family'),
  ('religious', 'Religious'),
  ('markets', 'Markets'),
  ('exhibitions', 'Exhibitions'),
  ('nightlife', 'Nightlife'),
  ('community', 'Community'),
  ('private-events', 'Private events'),
  ('concerts', 'Concerts'),
  ('festivals', 'Festivals'),
  ('gospel', 'Gospel'),
  ('stand-up', 'Stand-up'),
  ('football', 'Football'),
  ('church', 'Church')
) as v (slug, name)
where event_categories.slug = v.slug and event_categories.name is null;

-- ---------------------------------------------------------------------------
-- 4. service_categories
-- ---------------------------------------------------------------------------
alter table public.service_categories
  add column status public.taxonomy_status not null default 'published',
  add column image_public_id text,
  add column image_alt text,
  add column icon text,
  add column show_in_customer boolean not null default true,
  add column show_in_vendor boolean not null default true,
  add column updated_by uuid;

alter table public.service_categories
  add constraint service_categories_image_public_id_check
    check (image_public_id is null or (length(image_public_id) between 1 and 500
      and image_public_id !~ '\.\.' and image_public_id !~ '^/')),
  add constraint service_categories_image_alt_check
    check (image_alt is null or length(image_alt) <= 200),
  add constraint service_categories_icon_check
    check (icon is null or icon ~ '^[a-z0-9][a-z0-9-]{0,39}$');

-- Service verticals that were code constants (services.category / SERVICE_VERTICALS in the
-- API, vendor form and customer menu). Slugs are unchanged and already referenced by
-- services.category. Sort 10..80 keeps the previous display order.
insert into public.service_categories (slug, parent_slug, name, path, sort, status)
values
  ('beauty', null, 'Beauty & personal care', 'beauty', 10, 'published'),
  ('food-catering', null, 'Food & catering', 'food-catering', 20, 'published'),
  ('auto', null, 'Auto services', 'auto', 30, 'published'),
  ('printing-creative', null, 'Printing & creative', 'printing-creative', 40, 'published'),
  ('home-services', null, 'Home services', 'home-services', 50, 'published'),
  ('tech-services', null, 'Tech services', 'tech-services', 60, 'published'),
  ('cleaning', null, 'Cleaning', 'cleaning', 70, 'published'),
  ('tailoring', null, 'Tailoring', 'tailoring', 80, 'published'),
  -- New verticals start as draft: an admin publishes them when ready.
  ('logistics-delivery', null, 'Logistics & delivery', 'logistics-delivery', 90, 'draft'),
  ('packaging-supplies', null, 'Packaging & supplies', 'packaging-supplies', 100, 'draft')
on conflict (slug) do nothing;

-- Any pre-existing strategy-catalogue rows (scripts/seed_taxonomy.py) were never wired to
-- services.category, so they must not suddenly become selectable by vendors or visible
-- in the customer menu. They start as draft; an admin can publish the ones they want.
update public.service_categories
set status = 'draft'
where slug not in (
  'beauty', 'food-catering', 'auto', 'printing-creative', 'home-services',
  'tech-services', 'cleaning', 'tailoring', 'logistics-delivery', 'packaging-supplies'
);

-- ---------------------------------------------------------------------------
-- 5. Row level security + grants
-- Public read only of published rows visible in at least one app; writes only through
-- the API as service_role.
-- ---------------------------------------------------------------------------
drop policy if exists categories_public_select on public.categories;
create policy categories_public_select
  on public.categories
  for select
  using (status = 'published' and (show_in_customer or show_in_vendor));
comment on policy categories_public_select on public.categories is
  'Published category nodes visible in the customer or vendor app are publicly readable; '
  'draft/blocked rows are service_role (admin API) only.';

drop policy if exists event_categories_public_read on public.event_categories;
create policy event_categories_public_read
  on public.event_categories
  for select
  using (status = 'published' and (show_in_customer or show_in_vendor));
comment on policy event_categories_public_read on public.event_categories is
  'Published event categories visible in the customer or vendor app are publicly readable.';
drop policy if exists event_categories_admin_all on public.event_categories;

drop policy if exists service_categories_public_read on public.service_categories;
create policy service_categories_public_read
  on public.service_categories
  for select
  using (status = 'published' and is_active and (show_in_customer or show_in_vendor));
comment on policy service_categories_public_read on public.service_categories is
  'Published service categories visible in the customer or vendor app are publicly readable.';
drop policy if exists service_categories_admin_all on public.service_categories;

revoke insert, update, delete on table public.categories from anon, authenticated;
revoke insert, update, delete on table public.event_categories from anon, authenticated;
revoke insert, update, delete on table public.service_categories from anon, authenticated;
grant select on table public.categories, public.event_categories, public.service_categories
  to anon, authenticated, service_role;
grant insert, update, delete on table
  public.categories, public.event_categories, public.service_categories to service_role;
