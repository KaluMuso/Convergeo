-- M06-P06: Query analytics & zero-result mining.
-- Anonymized search + Ask query log feeding merchandising insights (top terms,
-- zero-result mining, Ask cost/day). user_id is nullable and trimmed after 30d
-- (Zambia DPA-aligned retention). Fire-and-forget writes are service-role only.
-- Down (manual): drop table public.search_query_log;

-- ---------------------------------------------------------------------------
-- search_query_log
-- ---------------------------------------------------------------------------
create table public.search_query_log (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('search', 'ask')),
  term text not null,
  normalized_term text not null,
  entity_counts jsonb not null default '{}'::jsonb,
  zero_result boolean not null default false,
  usd_micros bigint not null default 0 check (usd_micros >= 0),
  user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now())
);

create index search_query_log_kind_created_at_idx
  on public.search_query_log (kind, created_at desc);

create index search_query_log_zero_result_idx
  on public.search_query_log (created_at desc)
  where zero_result;

create index search_query_log_normalized_term_idx
  on public.search_query_log (normalized_term);

comment on table public.search_query_log is
  'Anonymized search + Ask query log; user_id trimmed after 30d (DPA). Feeds M13-P09 merchandising insights.';

comment on column public.search_query_log.kind is
  'search = FTS/RRF search query; ask = Ask Vergeo RAG question.';

comment on column public.search_query_log.entity_counts is
  'Result breakdown per entity kind (products/services/events/...) at query time.';

comment on column public.search_query_log.usd_micros is
  'Ask model spend in micro-dollars (0 for search rows).';

comment on column public.search_query_log.user_id is
  'Best-effort actor; NULLed by trim_search_pii after the 30-day retention window.';

-- ---------------------------------------------------------------------------
-- Row level security — admin read; service_role writes
-- ---------------------------------------------------------------------------
alter table public.search_query_log enable row level security;
alter table public.search_query_log force row level security;

create policy search_query_log_admin_select
  on public.search_query_log
  for select
  to authenticated
  using (public.has_role('admin'));

create policy search_query_log_service_role_all
  on public.search_query_log
  for all
  to service_role
  using (true)
  with check (true);

comment on policy search_query_log_admin_select on public.search_query_log is
  'Platform admins may read query analytics; writes are service_role only.';
comment on policy search_query_log_service_role_all on public.search_query_log is
  'Fire-and-forget query logger and the retention trim run as service_role.';

grant select on table public.search_query_log to authenticated;
grant select, insert, update, delete on table public.search_query_log to service_role;
