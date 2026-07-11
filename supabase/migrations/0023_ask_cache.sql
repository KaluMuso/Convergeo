-- M06-P02: Normalized-query response cache for Ask Vergeo (24h TTL).
--
-- Reversible rollback:
--   DROP TABLE IF EXISTS public.ask_cache;

-- ---------------------------------------------------------------------------
-- ask_cache (service-role only)
-- ---------------------------------------------------------------------------

create table public.ask_cache (
  normalized_query text primary key,
  answer jsonb not null,
  cited_ids uuid[] not null default '{}',
  expires_at timestamptz not null,
  created_at timestamptz not null default timezone('utc', now())
);

create index ask_cache_expires_at_idx
  on public.ask_cache (expires_at);

comment on table public.ask_cache is
  '24-hour TTL cache for Ask Vergeo answers keyed by normalized query text.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.ask_cache enable row level security;
alter table public.ask_cache force row level security;

create policy ask_cache_service_role_all
  on public.ask_cache
  for all
  to service_role
  using (true)
  with check (true);

comment on policy ask_cache_service_role_all on public.ask_cache is
  'Only service_role may read/write ask response cache rows.';

grant select, insert, update, delete on table public.ask_cache to service_role;
