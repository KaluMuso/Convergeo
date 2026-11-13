-- Delivery pricing by area pair (founder-approved 2026-11-13; growth blueprint §5,
-- logistics blueprint §6.6). Additive only.
--
--   1. public.areas            ~60 named Lusaka areas: aliases, approximate centroid, zone.
--   2. public.area_distances   precomputed road km + minutes between every ordered pair
--                              (vendor area -> customer area). Filled offline: the seed
--                              migration (20261113221000) writes an ESTIMATE
--                              (great-circle x 1.3); scripts/ops/build_area_distances.py
--                              regenerates it from an OSRM server. No routing service
--                              runs in production and no paid map API is ever called.
--   3. public.addresses        + area_slug (picked from the list) + address_type (home|work).
--   4. public.delivery_price_shadow_log   new fee next to the charged fee (shadow mode).
--   5. platform_config         area_pricing_shadow (ON), area_pricing_live (OFF),
--                              delivery_rain_mode (OFF), area_pricing_settings,
--                              delivery_time_bands; delivery_cutoffs moves 15:00 -> 14:00
--                              ("Order before 2 pm, get it today").
--
-- Down (manual, reverse order):
--   update public.platform_config set value = '["11:00", "15:00"]'::jsonb where key = 'delivery_cutoffs';
--   delete from public.platform_config where key in ('area_pricing_shadow', 'area_pricing_live',
--     'delivery_rain_mode', 'area_pricing_settings', 'delivery_time_bands');
--   drop table public.delivery_price_shadow_log;
--   alter table public.addresses drop column address_type, drop column area_slug;
--   drop table public.area_distances; drop table public.areas;

-- ---------------------------------------------------------------------------
-- 1. Areas
-- ---------------------------------------------------------------------------
create table if not exists public.areas (
  slug text primary key check (slug ~ '^[a-z0-9_]{2,40}$'),
  name text not null check (char_length(btrim(name)) between 2 and 80),
  aliases text[] not null default '{}'::text[],
  lat double precision not null check (lat between -90 and 90),
  lng double precision not null check (lng between -180 and 180),
  zone_key text not null references public.delivery_zones (zone_key),
  active boolean not null default true,
  centroid_source text not null default 'approximate, typed from general knowledge (not surveyed)',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

drop trigger if exists areas_set_updated_at on public.areas;
create trigger areas_set_updated_at
  before update on public.areas
  for each row execute function public.set_updated_at();

alter table public.areas enable row level security;
alter table public.areas force row level security;
-- The area picker is public (checkout and the address form); names are not personal data.
drop policy if exists areas_public_select on public.areas;
create policy areas_public_select
  on public.areas for select to anon, authenticated
  using (active);
drop policy if exists areas_admin_select on public.areas;
create policy areas_admin_select
  on public.areas for select to authenticated
  using (public.has_role('admin'));
revoke all on table public.areas from anon, authenticated;
grant select on table public.areas to anon, authenticated;
grant select, insert, update, delete on table public.areas to service_role;

comment on table public.areas is
  'Named Lusaka delivery areas for the area picker and area-pair pricing. '
  'Centroids are approximate; zone_key matches the landmark matcher bands.';

-- ---------------------------------------------------------------------------
-- 2. Area-pair distances (directed: from = shop area, to = customer area)
-- ---------------------------------------------------------------------------
create table if not exists public.area_distances (
  from_area text not null references public.areas (slug) on delete cascade,
  to_area text not null references public.areas (slug) on delete cascade,
  road_km numeric(6, 2) not null check (road_km >= 0 and road_km <= 500),
  minutes integer not null check (minutes >= 0 and minutes <= 600),
  source text not null check (char_length(source) between 3 and 120),
  manual_override boolean not null default false,
  computed_at timestamptz not null default timezone('utc', now()),
  primary key (from_area, to_area),
  check (from_area <> to_area)
);

alter table public.area_distances enable row level security;
alter table public.area_distances force row level security;
drop policy if exists area_distances_admin_select on public.area_distances;
create policy area_distances_admin_select
  on public.area_distances for select to authenticated
  using (public.has_role('admin'));
revoke all on table public.area_distances from anon, authenticated;
grant select on table public.area_distances to authenticated;
grant select, insert, update, delete on table public.area_distances to service_role;

comment on table public.area_distances is
  'Road distance and drive time between area centroids, computed offline. '
  'source says how (estimate vs OSRM); manual_override rows survive a refresh.';

-- ---------------------------------------------------------------------------
-- 3. Address: picked area + Home / Work
-- ---------------------------------------------------------------------------
alter table public.addresses
  add column if not exists area_slug text references public.areas (slug) on delete set null,
  add column if not exists address_type text not null default 'home';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'addresses_address_type_check'
  ) then
    alter table public.addresses
      add constraint addresses_address_type_check check (address_type in ('home', 'work'));
  end if;
end $$;

comment on column public.addresses.area_slug is
  'Area picked from public.areas; NULL = not chosen (the landmark matcher prices it).';
comment on column public.addresses.address_type is
  'home | work. Work addresses are only scheduled inside office hours (before 16:45).';

-- ---------------------------------------------------------------------------
-- 4. Shadow log: what the area-pair price would have been, next to the charged fee
-- ---------------------------------------------------------------------------
create table if not exists public.delivery_price_shadow_log (
  id uuid primary key default gen_random_uuid(),
  checkout_group_id uuid references public.checkout_groups (id) on delete set null,
  customer_area text,
  vendor_areas text[] not null default '{}'::text[],
  pickups integer not null default 0 check (pickups >= 0),
  route_km numeric(7, 2),
  time_band text,
  rain_mode boolean not null default false,
  charged_fee_ngwee bigint not null check (charged_fee_ngwee >= 0),
  area_fee_ngwee bigint check (area_fee_ngwee is null or area_fee_ngwee >= 0),
  mode text not null check (mode in ('shadow', 'live')),
  outcome text not null check (char_length(outcome) between 2 and 60),
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists delivery_price_shadow_log_created_idx
  on public.delivery_price_shadow_log (created_at desc);

alter table public.delivery_price_shadow_log enable row level security;
alter table public.delivery_price_shadow_log force row level security;
drop policy if exists delivery_price_shadow_log_admin_select on public.delivery_price_shadow_log;
create policy delivery_price_shadow_log_admin_select
  on public.delivery_price_shadow_log for select to authenticated
  using (public.has_role('admin'));
revoke all on table public.delivery_price_shadow_log from anon, authenticated;
grant select on table public.delivery_price_shadow_log to authenticated;
grant select, insert, update, delete on table public.delivery_price_shadow_log to service_role;

comment on table public.delivery_price_shadow_log is
  'Area-pair delivery fee computed next to the fee actually charged (no address text stored).';

-- ---------------------------------------------------------------------------
-- 5. Settings (editable without a deploy)
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  ('area_pricing_shadow', 'true'::jsonb,
   'Area-pair delivery pricing, shadow mode: compute and log the new fee next to the old one; '
   'charge the old zone fee.'),
  ('area_pricing_live', 'false'::jsonb,
   'Area-pair delivery pricing, live: charge the new consolidated fee. Keep OFF until the '
   'distance table is refreshed with OSRM and the shadow log looks right.'),
  ('delivery_rain_mode', 'false'::jsonb,
   'Rain switch (operations screen): multiplies the area-pair fee and widens windows by 30 min.'),
  ('area_pricing_settings',
   '{"base_per_km_ngwee": 400, "stop_fee_ngwee": 1300, "intra_area_km": 2.0,
     "min_fee_ngwee": 2500, "max_fee_ngwee": 20000, "rain_multiplier_bps": 12000,
     "zone_bounds": true, "quote_ttl_minutes": 30}'::jsonb,
   'fee = round_up_to_K5(base_per_km x road_km x time band x rain + stop_fee per shop). '
   'zone_bounds: floor = cheapest zone fee, cap = dearest zone fee per shop (until the table is trusted).'),
  ('delivery_time_bands',
   '[{"key": "morning_peak", "start": "07:00", "end": "09:00", "multiplier_bps": 15000},
     {"key": "midday", "start": "09:00", "end": "16:30", "multiplier_bps": 10000},
     {"key": "evening_peak", "start": "16:30", "end": "18:30", "multiplier_bps": 12000},
     {"key": "evening", "start": "18:30", "end": "20:00", "multiplier_bps": 11000}]'::jsonb,
   'Time-of-day multipliers (Africa/Lusaka) applied by the start of the promised delivery window. '
   'Outside every band: x1.0.')
on conflict (key) do nothing;

update public.platform_config
set value = '["11:00", "14:00"]'::jsonb,
    description = 'Daily delivery cut-offs (Africa/Lusaka): order by 11:00 -> 12:00-14:30; '
                  'by 14:00 -> 15:00-16:45 (work) or 17:00-19:30 (home). "Order before 2 pm, get it today."'
where key = 'delivery_cutoffs';
