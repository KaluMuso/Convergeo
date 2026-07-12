-- M16-P05: Unified analytics event schema (server source-of-truth over funnel + search).
-- Additive: a superset table `analytics_events` for events that have no dedicated
-- stream table (e.g. the client-mirrored product_view / PDP step), PLUS a read-only
-- view `analytics_event_stream` that union- s all three server streams into one
-- canonical shape so the full funnel (search -> product_view -> cart -> checkout ->
-- pay) is queryable end-to-end. The existing tables (0025 funnel_events, 0027
-- search_query_log) are UNCHANGED — their rows surface through the view, so no hot
-- write path changes. Server log is anonymized regardless of consent: no raw PII
-- column, and search rows expose normalized_term only (never the raw `term`).
-- Down (manual): drop view public.analytics_event_stream; drop table public.analytics_events;

-- ---------------------------------------------------------------------------
-- analytics_events — superset sink for events without a dedicated stream table
-- (client-mirrored product_view/PDP, generic funnel-adjacent events). Money values
-- inside `props` are integer ngwee. No raw PII column — anonymized regardless of
-- consent. Service-role write, admin read; no client/anon read of raw events.
-- ---------------------------------------------------------------------------
create table public.analytics_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null check (char_length(event_type) between 1 and 64),
  session_id uuid,
  user_id uuid references auth.users (id) on delete set null,
  entity_type text check (entity_type is null or char_length(entity_type) between 1 and 32),
  entity_id uuid,
  props jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index analytics_events_type_created_at_idx
  on public.analytics_events (event_type, created_at desc);

create index analytics_events_session_created_at_idx
  on public.analytics_events (session_id, created_at desc)
  where session_id is not null;

create index analytics_events_user_created_at_idx
  on public.analytics_events (user_id, created_at desc)
  where user_id is not null;

comment on table public.analytics_events is
  'M16-P05 superset analytics sink for events without a dedicated stream table (e.g. client-mirrored product_view/PDP). Anonymized: no raw PII column; money props are integer ngwee. Service-role write, admin read only.';

comment on column public.analytics_events.event_type is
  'Canonical event name (e.g. product_view, search, cart_add) — maps to a funnel step.';
comment on column public.analytics_events.props is
  'Structured, anonymized JSON payload. Any money value is integer ngwee. No raw PII.';

-- ---------------------------------------------------------------------------
-- Row level security — admin read; service_role writes; no client/anon read.
-- ---------------------------------------------------------------------------
alter table public.analytics_events enable row level security;
alter table public.analytics_events force row level security;

create policy analytics_events_admin_select
  on public.analytics_events
  for select
  to authenticated
  using (public.has_role('admin'));

create policy analytics_events_service_role_all
  on public.analytics_events
  for all
  to service_role
  using (true)
  with check (true);

comment on policy analytics_events_admin_select on public.analytics_events is
  'Platform admins may read raw analytics events; writes are service_role only.';
comment on policy analytics_events_service_role_all on public.analytics_events is
  'The unified analytics emit surface writes as service_role.';

grant select on table public.analytics_events to authenticated;
grant select, insert, update, delete on table public.analytics_events to service_role;

-- ---------------------------------------------------------------------------
-- analytics_event_stream — canonical read-only union of the three server streams.
-- One queryable shape for the end-to-end funnel. security_invoker = true so the
-- admin-read RLS of every base table still governs access through the view
-- (a non-admin authenticated caller is filtered to zero rows; anon has no grant).
-- Anonymized: search rows project normalized_term only — never the raw `term`.
-- ---------------------------------------------------------------------------
create view public.analytics_event_stream
with (security_invoker = true) as
  select
    ae.id,
    'events'::text        as source,
    ae.event_type,
    ae.session_id,
    ae.user_id,
    ae.entity_type,
    ae.entity_id,
    ae.props,
    ae.created_at
  from public.analytics_events ae
  union all
  select
    fe.id,
    'funnel'::text        as source,
    fe.stage              as event_type,
    fe.checkout_group_id  as session_id,
    fe.customer_id        as user_id,
    'checkout'::text      as entity_type,
    fe.checkout_group_id  as entity_id,
    fe.snapshot           as props,
    fe.created_at
  from public.funnel_events fe
  union all
  select
    sq.id,
    'search'::text        as source,
    sq.kind               as event_type,
    null::uuid            as session_id,
    sq.user_id,
    'query'::text         as entity_type,
    null::uuid            as entity_id,
    jsonb_build_object(
      'normalized_term', sq.normalized_term,
      'entity_counts', sq.entity_counts,
      'zero_result', sq.zero_result,
      'usd_micros', sq.usd_micros
    )                     as props,
    sq.created_at
  from public.search_query_log sq;

comment on view public.analytics_event_stream is
  'M16-P05 canonical union of analytics_events + funnel_events + search_query_log for end-to-end funnel queries (search -> product_view -> cart -> checkout -> pay). security_invoker: base-table admin-read RLS applies. Search rows expose normalized_term only (anonymized).';

grant select on public.analytics_event_stream to authenticated, service_role;
