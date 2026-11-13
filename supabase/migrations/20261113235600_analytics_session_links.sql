-- Convergeo Intelligence 1A-08: analytics_session_links (docs/plan/intelligence/stage1-plan.md,
-- §R-B "Sign-in linking", decision OD-2 = YES, 30-day retention).
--
-- Additive only. ONE new table; no existing table, view, function or policy is touched.
-- Nothing writes here unless feature flag analytics_v2_collect is ON and a signed-in,
-- non-opted-out customer calls POST /analytics/identify, so merging changes no behaviour.
--
--   * session_id (the anonymous v2 journey id) is the PRIMARY KEY: a session belongs to the
--     first account that claims it, and the same (session, user) pair is idempotent.
--   * user_id → auth.users is ON DELETE CASCADE: account deletion (DPA) removes the link.
--   * Raw events are NEVER back-filled with user_id; rollups join this table instead.
--   * Links are hard-deleted after 30 days by the rollups-gated v2 retention tick, the same
--     window as the raw event log, so a link never outlives the rows it explains.
--   * No PII: only two opaque ids and a timestamp. RLS + FORCE, service_role only: no grant to
--     anon/authenticated at all; the only write path is the authenticated API endpoint.
--
-- Down (manual, only after the 1A-08 code is reverted):
--   drop table if exists public.analytics_session_links;

create table if not exists public.analytics_session_links (
  session_id uuid primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  linked_at timestamptz not null default timezone('utc', now())
);

create index if not exists analytics_session_links_linked_at_brin
  on public.analytics_session_links using brin (linked_at);

comment on table public.analytics_session_links is
  'Convergeo Intelligence 1A-08: anonymous v2 session id -> customer, written only by POST /analytics/identify (flag analytics_v2_collect, consent on). Deleted at 30 days by the rollups-gated retention tick; cascades on account deletion. RLS FORCE, service_role only.';
comment on column public.analytics_session_links.session_id is
  'Anonymous rotating v2 session id (client-generated UUID). First account to claim it wins.';
comment on column public.analytics_session_links.user_id is
  'Server-resolved customer id from the verified JWT, never client-asserted. ON DELETE CASCADE.';

alter table public.analytics_session_links enable row level security;
alter table public.analytics_session_links force row level security;

drop policy if exists analytics_session_links_service_role_all on public.analytics_session_links;
create policy analytics_session_links_service_role_all
  on public.analytics_session_links
  for all
  to service_role
  using (true)
  with check (true);

comment on policy analytics_session_links_service_role_all on public.analytics_session_links is
  'The API identify endpoint and the retention job run as service_role. No client role has a grant.';

revoke all on table public.analytics_session_links from public, anon, authenticated;
grant select, insert, update, delete on table public.analytics_session_links to service_role;
