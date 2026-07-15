-- 0039 test: search_upsert_event projects events under their real category path.
-- Requires: 0001–0009, 0036 (events.category_slug + event_categories seed), 0039.
-- Run: supabase test db (pgTAP) after db reset.

begin;

set local search_path to public, extensions, auth;

select extensions.plan(2);

-- ---------------------------------------------------------------------------
-- Fixture seed (service_role bypasses RLS)
-- ---------------------------------------------------------------------------

set local role service_role;

create or replace function pg_temp.seed_auth_user(target_id uuid, email text)
returns void
language plpgsql
as $$
begin
  insert into auth.users (
    instance_id,
    id,
    aud,
    role,
    email,
    encrypted_password,
    email_confirmed_at,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at
  )
  values (
    '00000000-0000-0000-0000-000000000000',
    target_id,
    'authenticated',
    'authenticated',
    email,
    'test-password-hash',
    timezone('utc', now()),
    '{}'::jsonb,
    '{}'::jsonb,
    timezone('utc', now()),
    timezone('utc', now())
  );
end;
$$;

select pg_temp.seed_auth_user(
  '11111111-1111-1111-1111-111111111111',
  'event-cat@test.local'
);

insert into public.profiles (id, phone, display_name)
values ('11111111-1111-1111-1111-111111111111', '+260971000077', 'Event Cat Vendor');

insert into public.vendors (
  id,
  owner_user_id,
  slug,
  display_name,
  description,
  status,
  kyc_tier
)
values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
  'event-cat-shop',
  'Event Cat Shop',
  'Lusaka organiser',
  'active',
  2
);

-- Event WITH a category -> hierarchical 'events/<slug>' path (the events_search_sync
-- trigger projects it on insert).
insert into public.events (id, organiser_vendor_id, title, slug, category_slug, status)
values (
  '40404040-4040-4040-4040-404040404040',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Pottery Workshop',
  'pottery-workshop',
  'workshops',
  'published'
);

select extensions.is(
  (
    select category_path
    from public.search_documents
    where entity_kind = 'event'
      and entity_id = '40404040-4040-4040-4040-404040404040'
  ),
  'events/workshops',
  'categorised event indexes under events/<slug>'
);

-- Event WITHOUT a category -> bare 'events' (backward compatible with the prefix
-- filter, since 'events' still prefix-matches 'events/<slug>').
insert into public.events (id, organiser_vendor_id, title, slug, status)
values (
  '50505050-5050-5050-5050-505050505050',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Uncategorised Event',
  'uncategorised-event',
  'published'
);

select extensions.is(
  (
    select category_path
    from public.search_documents
    where entity_kind = 'event'
      and entity_id = '50505050-5050-5050-5050-505050505050'
  ),
  'events',
  'uncategorised event falls back to the bare events path'
);

select * from extensions.finish();

rollback;
