-- Convergeo Intelligence 1A-02: analytics v2 foundation (docs/plan/intelligence/stage1-plan.md).
--
-- Additive only. Creates ONE new table and inserts TWO default-OFF feature flags; no
-- existing table, view, function or policy is touched. While the flags are off nothing
-- writes here, so merging this migration changes no behaviour.
--
-- analytics_event_log — the v2 raw event log fed by POST /analytics/collect through the
-- bounded per-worker writer (plan §R-D). Design notes:
--   * event_id is the client-generated UUID and the PRIMARY KEY: `ON CONFLICT DO NOTHING`
--     makes beacon retries / double flushes free (idempotent ingest).
--   * Only two indexes (PK + BRIN on received_at): rollups scan one day by BRIN and the
--     retention sweep deletes by BRIN — every extra btree costs ~40 B/row (plan §R-G).
--   * Raw rows are hard-DELETED at 30 days by the rollups-gated sweep (1A-07), so person
--     links never outlive the 30-day DPA window and there is no NULLing UPDATE bloat.
--   * No FK to transactional tables (isolation, plan §R-D); user_id → auth.users is
--     ON DELETE SET NULL so account deletion (DPA) clears the link.
--   * Money is never stored here (authoritative tables only, plan §R-I); props is an
--     allowlisted jsonb (server-validated) capped at 2 KB.
--   * RLS + FORCE, service_role only: no grant to anon/authenticated at all. Admin reads
--     go through admin-guarded API endpoints over rollups (1B).
--
-- Flags (plan §F.1): analytics_v2_collect gates the API v2 ingest path; analytics_v2_rollups
-- gates v2 background jobs (retention sweeps, rollups, reports). Client tracking is the
-- build-time env NEXT_PUBLIC_ANALYTICS_V2_TRACKING (not a DB row).
--
-- Down (manual, run only after both flags are OFF and the 1A-03+ code is reverted):
--   drop table if exists public.analytics_event_log;
--   delete from public.feature_flags where flag in ('analytics_v2_collect', 'analytics_v2_rollups');

create table if not exists public.analytics_event_log (
  event_id uuid primary key,
  received_at timestamptz not null default timezone('utc', now()),
  client_ts timestamptz,
  event_name text not null check (event_name ~ '^[a-z][a-z0-9_]{0,63}$'),
  event_version smallint not null default 1 check (event_version between 1 and 100),
  source_app text not null check (source_app in ('customer', 'vendor', 'admin', 'server')),
  anon_id uuid,
  session_id uuid,
  user_id uuid references auth.users (id) on delete set null,
  seq integer check (seq is null or seq >= 0),
  page_key text check (page_key is null or page_key ~ '^[a-z0-9_.-]{1,48}$'),
  entity_type text check (entity_type is null or char_length(entity_type) between 1 and 32),
  entity_id uuid,
  props jsonb not null default '{}'::jsonb check (pg_column_size(props) <= 2048)
);

create index if not exists analytics_event_log_received_at_brin
  on public.analytics_event_log using brin (received_at);

comment on table public.analytics_event_log is
  'Convergeo Intelligence v2 raw event log (plan 1A-02). Written only by the API bounded writer when feature flag analytics_v2_collect is on. Idempotent on event_id. Raw rows deleted at 30 days (rollups-gated sweep). No money, no raw PII; props are server-allowlisted. RLS FORCE, service_role only.';
comment on column public.analytics_event_log.event_id is
  'Client-generated UUIDv4 (server-synthesised for v1 beacons); primary key = dedup key.';
comment on column public.analytics_event_log.anon_id is
  'Pseudonymous visitor id (localStorage); NULL in counts-only (opt-out / GPC) mode.';
comment on column public.analytics_event_log.session_id is
  'Rotating session id (30-min inactivity rule). Session end is always an ESTIMATE (plan §R-A).';
comment on column public.analytics_event_log.user_id is
  'Server-resolved customer id only (never client-asserted). ON DELETE SET NULL for DPA deletion.';
comment on column public.analytics_event_log.page_key is
  'Page template key (pdp, plp, search, …) — never a URL, slug or query string.';

alter table public.analytics_event_log enable row level security;
alter table public.analytics_event_log force row level security;

drop policy if exists analytics_event_log_service_role_all on public.analytics_event_log;
create policy analytics_event_log_service_role_all
  on public.analytics_event_log
  for all
  to service_role
  using (true)
  with check (true);

comment on policy analytics_event_log_service_role_all on public.analytics_event_log is
  'The API bounded analytics writer and the retention/rollup jobs run as service_role. No client role has a grant.';

revoke all on table public.analytics_event_log from public, anon, authenticated;
grant select, insert, update, delete on table public.analytics_event_log to service_role;

insert into public.feature_flags (flag, enabled, description) values
  (
    'analytics_v2_collect',
    false,
    'Convergeo Intelligence 1A: API analytics v2 ingest (bounded off-request writer, in-process '
    'limiter, analytics_event_log, off-loop server emits, search-term redaction). OFF = exact v1 '
    'behaviour. Kill switch: set false (takes effect within ~15 s).'
  ),
  (
    'analytics_v2_rollups',
    false,
    'Convergeo Intelligence 1A/1B/1C: v2 background jobs (30-day raw-log delete, listing-view '
    'dedup purge, search-term scrub, daily rollups, reports). OFF = ticks skip; v1 retention unchanged.'
  )
on conflict (flag) do nothing;
