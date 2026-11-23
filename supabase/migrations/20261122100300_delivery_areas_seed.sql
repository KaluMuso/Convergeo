-- Seed: Lusaka delivery areas and an INTERIM area-pair distance table.
--
-- Areas: docs/ops/lusaka-delivery-reference-prices.md (sections 3-5) plus the
-- landmark keyword list in services/api/app/routers/checkout.py. zone_key equals
-- the band the landmark matcher gives the same name, so choosing an area never
-- changes the zone fee charged today. Centroids are APPROXIMATE (typed from
-- general knowledge, each plausibly 0.5-1 km off) and must be checked on a map.
--
-- Distances: ESTIMATE - REFRESH WITH OSRM. OpenStreetMap / OSRM data could not be
-- downloaded where this was built, so every ordered pair is
--     road_km = great-circle km between centroids x 1.3 (road factor)
--     minutes = ceil(road_km / 25 km/h x 60)            (motorbike, city average)
-- and is marked source = 'estimate: great-circle x 1.3 - refresh with OSRM'.
-- Regenerate with: scripts/ops/build_area_distances.py --osrm http://<osrm>:5000
-- (rows with manual_override = true are kept).
--
-- Down (manual): delete from public.area_distances; delete from public.areas;

insert into public.areas (slug, name, zone_key, lat, lng, aliases) values
  -- Band A (central)
  ('cbd', 'CBD / Cairo Road', 'lusaka_a', -15.4167, 28.2833, array['cbd', 'cairo road', 'city centre', 'central']),
  ('longacres', 'Longacres', 'lusaka_a', -15.4050, 28.3080, array['long acres']),
  ('rhodes_park', 'Rhodes Park', 'lusaka_a', -15.4060, 28.2990, array[]::text[]),
  ('northmead', 'Northmead', 'lusaka_a', -15.3990, 28.3040, array[]::text[]),
  ('fairview', 'Fairview', 'lusaka_a', -15.4100, 28.2920, array[]::text[]),
  ('woodlands', 'Woodlands', 'lusaka_a', -15.4300, 28.3050, array[]::text[]),
  ('woodlands_extension', 'Woodlands Extension', 'lusaka_a', -15.4420, 28.3230, array['woodlands ext']),
  ('kabwata', 'Kabwata', 'lusaka_a', -15.4450, 28.2900, array[]::text[]),
  ('olympia', 'Olympia Park', 'lusaka_a', -15.3950, 28.3160, array['olympia']),
  ('roma', 'Roma', 'lusaka_a', -15.3850, 28.3050, array['roma park']),
  ('kalingalinga', 'Kalingalinga', 'lusaka_a', -15.4100, 28.3200, array[]::text[]),
  ('emmasdale', 'Emmasdale', 'lusaka_a', -15.3770, 28.2650, array[]::text[]),
  ('kabulonga', 'Kabulonga', 'lusaka_a', -15.4250, 28.3270, array[]::text[]),
  ('manda_hill', 'Manda Hill', 'lusaka_a', -15.3970, 28.3070, array[]::text[]),
  ('east_park', 'East Park Mall', 'lusaka_a', -15.3930, 28.3200, array['east park']),
  ('arcades', 'Arcades', 'lusaka_a', -15.4000, 28.3230, array[]::text[]),
  ('levy_junction', 'Levy Junction', 'lusaka_a', -15.4120, 28.2890, array['levy mall']),
  ('thorn_park', 'Thorn Park', 'lusaka_a', -15.4180, 28.2700, array['thornpark']),
  ('uth', 'UTH / hospital area', 'lusaka_a', -15.4290, 28.3110, array['university teaching hospital']),
  ('unza', 'UNZA (Great East Road)', 'lusaka_a', -15.3920, 28.3290, array['university of zambia']),
  ('ridgeway', 'Ridgeway', 'lusaka_a', -15.4220, 28.2990, array[]::text[]),
  ('villa_elizabetta', 'Villa Elizabetta', 'lusaka_a', -15.4060, 28.2700, array[]::text[]),
  -- Band B (mid-ring)
  ('chilenje', 'Chilenje', 'lusaka_b', -15.4600, 28.3000, array['chilenje south']),
  ('libala', 'Libala', 'lusaka_b', -15.4450, 28.3100, array['libala south']),
  ('kamwala', 'Kamwala', 'lusaka_b', -15.4300, 28.2850, array['kamwala south']),
  ('makeni', 'Makeni', 'lusaka_b', -15.4600, 28.2500, array[]::text[]),
  ('matero', 'Matero', 'lusaka_b', -15.3700, 28.2400, array[]::text[]),
  ('mtendere', 'Mtendere', 'lusaka_b', -15.4050, 28.3530, array['mtendere east']),
  ('ibex_hill', 'Ibex Hill', 'lusaka_b', -15.4300, 28.3600, array['ibex']),
  ('chelstone', 'Chelstone', 'lusaka_b', -15.3750, 28.3550, array['chelston']),
  ('chainda', 'Chainda', 'lusaka_b', -15.3850, 28.3650, array[]::text[]),
  ('kalundu', 'Kalundu', 'lusaka_b', -15.3880, 28.3400, array[]::text[]),
  ('lilayi', 'Lilayi', 'lusaka_b', -15.5200, 28.3000, array[]::text[]),
  ('chawama', 'Chawama', 'lusaka_b', -15.4550, 28.2700, array[]::text[]),
  ('ngombe', 'Ng''ombe', 'lusaka_b', -15.3780, 28.3200, array['ngombe']),
  ('john_laing', 'John Laing', 'lusaka_b', -15.4450, 28.2650, array[]::text[]),
  ('chaisa', 'Chaisa', 'lusaka_b', -15.3850, 28.2650, array[]::text[]),
  ('bauleni', 'Bauleni', 'lusaka_b', -15.4400, 28.3450, array[]::text[]),
  ('kabanana', 'Kabanana', 'lusaka_b', -15.3550, 28.2650, array[]::text[]),
  ('garden', 'Garden Compound', 'lusaka_b', -15.3850, 28.2750, array['garden compound']),
  ('mandevu', 'Mandevu', 'lusaka_b', -15.3650, 28.2600, array[]::text[]),
  ('marapodi', 'Marapodi', 'lusaka_b', -15.3800, 28.2550, array[]::text[]),
  ('kaunda_square', 'Kaunda Square', 'lusaka_b', -15.3920, 28.3550, array[]::text[]),
  ('avondale', 'Avondale', 'lusaka_b', -15.3850, 28.3500, array[]::text[]),
  ('munali', 'Munali', 'lusaka_b', -15.3980, 28.3450, array[]::text[]),
  ('misisi', 'Misisi', 'lusaka_b', -15.4500, 28.2900, array[]::text[]),
  ('linda', 'Linda', 'lusaka_b', -15.4800, 28.2700, array['linda compound']),
  ('salama_park', 'Salama Park', 'lusaka_b', -15.4650, 28.3350, array[]::text[]),
  ('jack', 'Jack Compound', 'lusaka_b', -15.4450, 28.2450, array['jack compound']),
  ('lusaka_west', 'Lusaka West', 'lusaka_b', -15.4200, 28.2000, array[]::text[]),
  ('chunga', 'Chunga', 'lusaka_b', -15.3600, 28.2350, array[]::text[]),
  ('meanwood', 'Meanwood / Kwamwena', 'lusaka_b', -15.4950, 28.3400, array['kwamwena', 'meanwood kwamwena']),
  ('twin_palm', 'Twin Palm', 'lusaka_b', -15.4500, 28.3600, array[]::text[]),
  -- Band C (outer)
  ('chalala', 'Chalala', 'lusaka_c', -15.4850, 28.3700, array[]::text[]),
  ('leopards_hill', 'Leopards Hill', 'lusaka_c', -15.4600, 28.4000, array[]::text[]),
  ('chilanga', 'Chilanga', 'lusaka_c', -15.5600, 28.2700, array[]::text[]),
  ('kkia', 'Airport (KKIA)', 'lusaka_c', -15.3310, 28.4520, array['airport', 'kkia', 'kenneth kaunda airport']),
  ('chongwe_road', 'Great East Road towards Chongwe', 'lusaka_c', -15.3600, 28.4300, array['chongwe']),
  ('kafue_road', 'Kafue Road (south)', 'lusaka_c', -15.5000, 28.2600, array['kafue road']),
  ('kanyama', 'Kanyama', 'lusaka_c', -15.4400, 28.2500, array[]::text[]),
  ('foxdale', 'Foxdale', 'lusaka_c', -15.3500, 28.3200, array[]::text[]),
  ('state_lodge', 'State Lodge', 'lusaka_c', -15.4700, 28.4200, array[]::text[]),
  ('ngwerere', 'Ngwerere', 'lusaka_c', -15.3000, 28.3300, array[]::text[])
on conflict (slug) do nothing;

insert into public.area_distances (from_area, to_area, road_km, minutes, source)
select
  a.slug,
  b.slug,
  round((g.km * 1.3)::numeric, 2),
  ceil(g.km * 1.3 / 25.0 * 60.0)::integer,
  'estimate: great-circle x 1.3 - refresh with OSRM'
from public.areas a
cross join public.areas b
cross join lateral (
  select 2 * 6371.0 * asin(sqrt(
    power(sin(radians(b.lat - a.lat) / 2), 2)
    + cos(radians(a.lat)) * cos(radians(b.lat)) * power(sin(radians(b.lng - a.lng) / 2), 2)
  )) as km
) g
where a.slug <> b.slug
on conflict (from_area, to_area) do nothing;
