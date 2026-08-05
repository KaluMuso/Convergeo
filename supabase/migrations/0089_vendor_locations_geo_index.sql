-- R02 geo-discovery: bounding-box prefilter index for nearby branch queries.
-- PostGIS is not installed (ADR-R02-04-B); haversine runs on the survivors.

create index if not exists vendor_locations_lat_lng_idx
  on public.vendor_locations (lat, lng);

comment on index public.vendor_locations_lat_lng_idx is
  'Bounding-box prefilter for /search/nearby and directory radius filters (R02 §3.6).';
