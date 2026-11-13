-- Admin-governed infinite home feed, ad placements and sponsored carousel slides.
--
-- Additive only: four new tables, three functions, two triggers and a seed of
-- default feed sections. No existing object is altered.
--
-- Access model: every table is service-role only (RLS enabled + forced, client
-- grants revoked). The public feed (`GET /home/feed`) and admin CRUD both run in
-- the API with the service-role key after the API's own authz checks; browsers
-- never read these tables directly, so a disabled or out-of-window placement can
-- never leak through PostgREST.
--
-- State machine: `ad_placements.status` moves only through
-- `public.transition_ad_placement(...)`, which validates the edge, locks the row,
-- and appends to `ad_placement_transitions` (the API additionally writes the
-- admin `audit_log` row via its audited admin route). A BEFORE UPDATE trigger rejects any
-- raw status UPDATE that does not come from that function.
--
-- Down (manual, reversible — no existing data is touched):
--   drop function if exists public.record_ad_placement_events(uuid, date, integer, integer);
--   drop function if exists public.transition_ad_placement(uuid, text, uuid, text);
--   drop table if exists public.ad_placement_daily_stats;
--   drop table if exists public.ad_placement_transitions;
--   drop table if exists public.ad_placements;   -- also drops guard trigger
--   drop function if exists public.guard_ad_placement_status();
--   drop table if exists public.home_feed_sections;

-- ---------------------------------------------------------------------------
-- home_feed_sections
-- ---------------------------------------------------------------------------
create table public.home_feed_sections (
  id uuid primary key default gen_random_uuid(),
  key text not null unique check (key ~ '^[a-z][a-z0-9_]{2,63}$'),
  section_type text not null check (
    section_type in (
      'category',    -- one category subtree (config.category_path)
      'collection',  -- manual list of listing ids (config.listing_ids)
      'rule',        -- rule-based catalogue query (config.rule)
      'services',    -- services browse rail
      'events',      -- upcoming events (config.within_days)
      'vendors',     -- top-rated vendors
      'for_you',     -- personalised for signed-in users, trending for guests
      'ad_slot'      -- filled by an active feed_slot ad placement
    )
  ),
  layout text not null default 'rail' check (layout in ('rail', 'grid', 'banner', 'ad')),
  -- Either an i18n message key (catalog namespace) or per-locale text, or both
  -- (per-locale text wins for that locale; key is the fallback).
  title_key text check (title_key is null or title_key ~ '^[a-zA-Z0-9_.]{1,120}$'),
  title_i18n jsonb not null default '{}'::jsonb check (jsonb_typeof(title_i18n) = 'object'),
  config jsonb not null default '{}'::jsonb check (jsonb_typeof(config) = 'object'),
  position integer not null default 0,
  enabled boolean not null default true,
  starts_at timestamptz,
  ends_at timestamptz,
  audience text not null default 'all' check (audience in ('all', 'guest', 'signed_in')),
  created_by uuid,
  updated_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint home_feed_sections_window_valid check (
    starts_at is null or ends_at is null or ends_at > starts_at
  ),
  constraint home_feed_sections_title_present check (
    title_key is not null or title_i18n <> '{}'::jsonb or section_type = 'ad_slot'
  )
);

create index home_feed_sections_position_idx
  on public.home_feed_sections (position, id) where enabled;

create trigger home_feed_sections_set_updated_at
  before update on public.home_feed_sections
  for each row execute function public.set_updated_at();

alter table public.home_feed_sections enable row level security;
alter table public.home_feed_sections force row level security;
revoke all on public.home_feed_sections from public, anon, authenticated;
grant select, insert, update, delete on public.home_feed_sections to service_role;

comment on table public.home_feed_sections is
  'Admin-ordered home feed sections; resolved server-side by GET /home/feed. Service role only.';

-- ---------------------------------------------------------------------------
-- ad_placements
-- ---------------------------------------------------------------------------
create table public.ad_placements (
  id uuid primary key default gen_random_uuid(),
  advertiser_kind text not null check (advertiser_kind in ('vendor', 'business', 'external')),
  advertiser_vendor_id uuid references public.vendors (id) on delete set null,
  advertiser_name text not null check (length(trim(advertiser_name)) between 2 and 120),
  placement_type text not null check (placement_type in ('feed_slot', 'carousel_slide')),
  image_public_id text not null check (image_public_id ~ '^[A-Za-z0-9_./-]{1,255}$'),
  headline text not null check (length(trim(headline)) between 2 and 120),
  body text check (body is null or length(body) <= 280),
  cta_label text check (cta_label is null or length(cta_label) between 1 and 40),
  -- Internal app route ('/…', never protocol-relative) or https URL. The API
  -- additionally enforces the external host allow-list.
  cta_href text not null check (
    (cta_href ~ '^/[^/\\]' or cta_href = '/') or cta_href ~ '^https://[A-Za-z0-9.-]+(/|$|\?)'
  ),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  priority integer not null default 0,
  -- Record only: no payment processing happens here.
  paid_amount_ngwee bigint not null default 0 check (paid_amount_ngwee >= 0),
  payment_reference text check (
    payment_reference is null or payment_reference ~ '^[-._A-Za-z0-9]{1,80}$'
  ),
  status text not null default 'draft'
    check (status in ('draft', 'scheduled', 'active', 'paused', 'ended')),
  enabled boolean not null default true,
  created_by uuid,
  updated_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ad_placements_window_valid check (ends_at > starts_at),
  constraint ad_placements_vendor_advertiser check (
    advertiser_kind <> 'vendor' or advertiser_vendor_id is not null
  )
);

create index ad_placements_live_idx
  on public.ad_placements (placement_type, starts_at, ends_at)
  where enabled and status in ('scheduled', 'active');

create trigger ad_placements_set_updated_at
  before update on public.ad_placements
  for each row execute function public.set_updated_at();

create function public.guard_ad_placement_status() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.status <> 'draft' then
      raise exception 'Ad placements must be created as draft' using errcode = '23514';
    end if;
    return new;
  end if;
  if new.status is distinct from old.status
     and coalesce(current_setting('app.ad_placement_transition', true), '') <> 'on' then
    raise exception 'Ad placement status changes must use transition_ad_placement'
      using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke all on function public.guard_ad_placement_status() from public, anon, authenticated;

create trigger ad_placements_guard_status
  before insert or update on public.ad_placements
  for each row execute function public.guard_ad_placement_status();

alter table public.ad_placements enable row level security;
alter table public.ad_placements force row level security;
revoke all on public.ad_placements from public, anon, authenticated;
grant select, insert, update, delete on public.ad_placements to service_role;

comment on table public.ad_placements is
  'Sponsored feed slots and carousel slides. Customer-visible only when enabled, '
  'status in (scheduled, active) and now() within [starts_at, ends_at). Service role only.';

-- ---------------------------------------------------------------------------
-- ad_placement_transitions (append-only audit of the status machine)
-- ---------------------------------------------------------------------------
create table public.ad_placement_transitions (
  id uuid primary key default gen_random_uuid(),
  placement_id uuid not null references public.ad_placements (id) on delete cascade,
  from_status text not null,
  to_status text not null,
  actor uuid,
  reason text check (reason is null or length(reason) <= 500),
  at timestamptz not null default now()
);

create index ad_placement_transitions_placement_idx
  on public.ad_placement_transitions (placement_id, at desc);

alter table public.ad_placement_transitions enable row level security;
alter table public.ad_placement_transitions force row level security;
revoke all on public.ad_placement_transitions from public, anon, authenticated;
grant select, insert on public.ad_placement_transitions to service_role;

-- ---------------------------------------------------------------------------
-- ad_placement_daily_stats (aggregated impression / click counters)
-- ---------------------------------------------------------------------------
create table public.ad_placement_daily_stats (
  placement_id uuid not null references public.ad_placements (id) on delete cascade,
  day date not null,
  impressions bigint not null default 0 check (impressions >= 0),
  clicks bigint not null default 0 check (clicks >= 0),
  updated_at timestamptz not null default now(),
  primary key (placement_id, day)
);

alter table public.ad_placement_daily_stats enable row level security;
alter table public.ad_placement_daily_stats force row level security;
revoke all on public.ad_placement_daily_stats from public, anon, authenticated;
grant select, insert, update on public.ad_placement_daily_stats to service_role;

-- ---------------------------------------------------------------------------
-- transition_ad_placement — the only path that changes ad_placements.status
-- ---------------------------------------------------------------------------
create function public.transition_ad_placement(
  p_placement_id uuid,
  p_to_status text,
  p_actor uuid,
  p_reason text default null
)
returns public.ad_placements
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_row public.ad_placements;
  updated_row public.ad_placements;
  allowed text[];
begin
  select * into current_row
  from public.ad_placements
  where id = p_placement_id
  for update;

  if not found then
    raise exception 'Ad placement not found' using errcode = 'P0002';
  end if;

  allowed := case current_row.status
    when 'draft' then array['scheduled']
    when 'scheduled' then array['active', 'paused', 'draft', 'ended']
    when 'active' then array['paused', 'ended']
    when 'paused' then array['active', 'scheduled', 'ended']
    else array[]::text[]
  end;

  if not (p_to_status = any(allowed)) then
    raise exception 'Invalid ad placement transition % -> %', current_row.status, p_to_status
      using errcode = '23514';
  end if;

  if p_to_status = 'active' and current_row.ends_at <= now() then
    raise exception 'Cannot activate an ad placement whose window has ended'
      using errcode = '23514';
  end if;

  perform pg_catalog.set_config('app.ad_placement_transition', 'on', true);
  update public.ad_placements
     set status = p_to_status,
         updated_by = p_actor
   where id = p_placement_id
  returning * into updated_row;
  perform pg_catalog.set_config('app.ad_placement_transition', 'off', true);

  insert into public.ad_placement_transitions (placement_id, from_status, to_status, actor, reason)
  values (p_placement_id, current_row.status, p_to_status, p_actor, p_reason);

  return updated_row;
end;
$$;

revoke all on function public.transition_ad_placement(uuid, text, uuid, text)
  from public, anon, authenticated;
grant execute on function public.transition_ad_placement(uuid, text, uuid, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- record_ad_placement_events — bounded daily aggregate increment
-- ---------------------------------------------------------------------------
create function public.record_ad_placement_events(
  p_placement_id uuid,
  p_day date,
  p_impressions integer,
  p_clicks integer
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_impressions < 0 or p_clicks < 0 or p_impressions > 50 or p_clicks > 20 then
    raise exception 'invalid ad event counts' using errcode = '22023';
  end if;
  if p_impressions = 0 and p_clicks = 0 then
    return 0;
  end if;

  -- Only live placements accrue counts; stale beacons for ended/disabled ads are dropped.
  if not exists (
    select 1 from public.ad_placements ap
    where ap.id = p_placement_id
      and ap.enabled
      and ap.status in ('scheduled', 'active')
      and now() >= ap.starts_at
      and now() < ap.ends_at
  ) then
    return 0;
  end if;

  insert into public.ad_placement_daily_stats as s (placement_id, day, impressions, clicks)
  values (p_placement_id, p_day, p_impressions, p_clicks)
  on conflict (placement_id, day) do update
    set impressions = s.impressions + excluded.impressions,
        clicks = s.clicks + excluded.clicks,
        updated_at = now();
  return 1;
end;
$$;

revoke all on function public.record_ad_placement_events(uuid, date, integer, integer)
  from public, anon, authenticated;
grant execute on function public.record_ad_placement_events(uuid, date, integer, integer)
  to service_role;

-- ---------------------------------------------------------------------------
-- Default feed sequence (only sections that resolve to non-empty data render)
-- ---------------------------------------------------------------------------
insert into public.home_feed_sections (key, section_type, layout, title_key, config, position)
values
  ('for_you', 'for_you', 'rail', 'home.feed.sections.forYou', '{"limit": 12}'::jsonb, 10),
  ('services_near_you', 'services', 'rail', 'home.feed.sections.servicesNearYou',
    '{"limit": 8, "view_all_href": "/services"}'::jsonb, 20),
  ('best_electronics', 'rule', 'rail', 'home.feed.sections.bestElectronics',
    '{"limit": 12, "rule": {"category_paths": ["electronics"], "sort": "top_rated"}, "view_all_href": "/c/electronics"}'::jsonb, 30),
  ('ad_slot_1', 'ad_slot', 'ad', null, '{}'::jsonb, 35),
  ('best_fashion', 'rule', 'rail', 'home.feed.sections.bestFashion',
    '{"limit": 12, "rule": {"category_paths": ["fashion"], "sort": "top_rated"}, "view_all_href": "/c/fashion"}'::jsonb, 40),
  ('mens', 'category', 'rail', 'home.feed.sections.mens',
    '{"limit": 12, "category_path": "fashion/mens-clothing"}'::jsonb, 50),
  ('womens', 'category', 'rail', 'home.feed.sections.womens',
    '{"limit": 12, "category_path": "fashion/womens-clothing"}'::jsonb, 60),
  ('kids', 'category', 'rail', 'home.feed.sections.kids',
    '{"limit": 12, "category_path": "fashion/kids-clothing"}'::jsonb, 70),
  ('ad_slot_2', 'ad_slot', 'ad', null, '{}'::jsonb, 75),
  ('under_k100', 'rule', 'grid', 'home.feed.sections.underK100',
    '{"limit": 12, "rule": {"price_max_ngwee": 10000, "sort": "cheapest"}}'::jsonb, 80),
  ('tech_gadgets', 'rule', 'rail', 'home.feed.sections.techGadgets',
    '{"limit": 12, "rule": {"category_paths": ["electronics/phone-accessories", "electronics/gaming", "electronics/cameras", "electronics/small-appliances"], "sort": "newest"}}'::jsonb, 90),
  ('seasonal_summer', 'rule', 'rail', 'home.feed.sections.seasonalSummer',
    '{"limit": 12, "rule": {"keywords": ["summer", "fan", "cooler", "sandal", "swim", "sun", "solar", "hat"], "sort": "relevance"}}'::jsonb, 100),
  ('events_this_week', 'events', 'rail', 'home.feed.sections.eventsThisWeek',
    '{"limit": 8, "within_days": 7, "view_all_href": "/events"}'::jsonb, 110),
  ('new_arrivals', 'rule', 'grid', 'home.feed.sections.newArrivals',
    '{"limit": 12, "rule": {"new_within_days": 14, "sort": "newest"}, "view_all_href": "/c/all"}'::jsonb, 120),
  ('trending_now', 'rule', 'rail', 'home.feed.sections.trending',
    '{"limit": 12, "rule": {"sort": "trending"}}'::jsonb, 130),
  ('top_vendors', 'vendors', 'rail', 'home.feed.sections.topVendors',
    '{"limit": 8, "view_all_href": "/directory"}'::jsonb, 140)
on conflict (key) do nothing;
