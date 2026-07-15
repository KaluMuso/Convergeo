-- M10 follow-up: give event instances an explicit end time.
--
-- Why: instances previously carried only `starts_at`, forcing every consumer to
-- fabricate an end from a fixed 2h assumption. That made three behaviours wrong
-- for anything longer than ~2h (multi-day festivals, all-day markets):
--   * escrow release keyed off `starts_at + 24h`, so a 3-day event's funds
--     released on day one, mid-event (services/api/.../escrow/event_release.py);
--   * `.ics` DTEND was always `starts_at + 2h` (routers/event_ics.py);
--   * public discovery dropped an event the moment it STARTED, not when it
--     ended (routers/events_public.py `_upcoming_instances`).
--
-- Additive + reversible (convention D6). `ends_at` is nullable so existing rows
-- and older API clients keep working; consumers coalesce NULL to a per-purpose
-- fallback (escrow -> starts_at, unchanged legacy money timing; ics/discovery
-- -> starts_at + 2h display default). Historical rows are backfilled to a
-- concrete +2h end so their data is self-consistent.
--
-- Down: alter table public.event_instances drop column ends_at;

alter table public.event_instances
  add column ends_at timestamptz;

alter table public.event_instances
  add constraint event_instances_ends_after_starts_chk
  check (ends_at is null or ends_at > starts_at);

-- Backfill existing instances to the prior implicit 2h duration.
update public.event_instances
  set ends_at = starts_at + interval '2 hours'
  where ends_at is null;

create index event_instances_ends_at_idx on public.event_instances (ends_at);

comment on column public.event_instances.ends_at is
  'Event instance end time (UTC). Nullable for backward compatibility; consumers '
  'fall back to starts_at (escrow) or starts_at + 2h (ics/discovery) when null. '
  'Enables end-anchored escrow release, accurate .ics DTEND, and end-based '
  'discovery cutoff so an in-progress event stays listed until it actually ends.';
