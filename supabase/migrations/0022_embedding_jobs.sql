-- M06-P01: Async embedding job queue for search_documents semantic lane.
--
-- Reversible rollback:
--   DROP TRIGGER IF EXISTS search_documents_embedding_enqueue ON public.search_documents;
--   DROP FUNCTION IF EXISTS public.embedding_jobs_enqueue_trigger();
--   DROP FUNCTION IF EXISTS public.embedding_enqueue_document(uuid, text, uuid);
--   DROP FUNCTION IF EXISTS public.claim_embedding_jobs(integer);
--   DROP TABLE IF EXISTS public.embedding_jobs;

-- ---------------------------------------------------------------------------
-- embedding_jobs queue (service-role / admin only)
-- ---------------------------------------------------------------------------

create table public.embedding_jobs (
  id uuid primary key default gen_random_uuid(),
  search_document_id uuid not null references public.search_documents (id) on delete cascade,
  entity_kind text not null
    check (entity_kind in ('product', 'listing', 'service', 'event', 'vendor')),
  entity_id uuid not null,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'done', 'dead')),
  attempts integer not null default 0 check (attempts >= 0),
  last_error text,
  batch_cost_usd numeric(12, 8),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  processed_at timestamptz
);

create index embedding_jobs_status_created_idx
  on public.embedding_jobs (status, created_at);

create index embedding_jobs_entity_idx
  on public.embedding_jobs (entity_kind, entity_id);

create unique index embedding_jobs_active_entity_uidx
  on public.embedding_jobs (entity_kind, entity_id)
  where status in ('queued', 'processing');

create trigger embedding_jobs_set_updated_at
  before update on public.embedding_jobs
  for each row
  execute function public.set_updated_at();

comment on table public.embedding_jobs is
  'Queue for async 384-dim search_documents.embedding backfill and publish/update refresh.';

-- ---------------------------------------------------------------------------
-- Enqueue helpers (security definer)
-- ---------------------------------------------------------------------------

create or replace function public.embedding_enqueue_document(
  p_search_document_id uuid,
  p_entity_kind text,
  p_entity_id uuid
)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  update public.embedding_jobs
  set
    search_document_id = p_search_document_id,
    status = 'queued',
    attempts = 0,
    last_error = null,
    batch_cost_usd = null,
    processed_at = null,
    updated_at = timezone('utc', now())
  where entity_kind = p_entity_kind
    and entity_id = p_entity_id
    and status in ('done', 'dead');

  insert into public.embedding_jobs (
    search_document_id,
    entity_kind,
    entity_id,
    status
  )
  select p_search_document_id, p_entity_kind, p_entity_id, 'queued'
  where not exists (
    select 1
    from public.embedding_jobs ej
    where ej.entity_kind = p_entity_kind
      and ej.entity_id = p_entity_id
      and ej.status in ('queued', 'processing')
  );
end;
$$;

comment on function public.embedding_enqueue_document(uuid, text, uuid) is
  'Idempotently enqueue one embedding job per entity; re-queues done/dead rows on content refresh.';

create or replace function public.embedding_jobs_enqueue_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    return old;
  end if;

  if new.is_public is distinct from true then
    return new;
  end if;

  if tg_op = 'UPDATE'
    and old.is_public is not distinct from true
    and old.title is not distinct from new.title
    and old.body is not distinct from new.body
    and old.locale_terms is not distinct from new.locale_terms
    and new.embedding is not null then
    return new;
  end if;

  perform public.embedding_enqueue_document(new.id, new.entity_kind, new.entity_id);
  return new;
end;
$$;

create trigger search_documents_embedding_enqueue
  after insert or update on public.search_documents
  for each row
  execute function public.embedding_jobs_enqueue_trigger();

-- ---------------------------------------------------------------------------
-- Atomic claim for internal batch tick (≤64 rows, SKIP LOCKED)
-- ---------------------------------------------------------------------------

create or replace function public.claim_embedding_jobs(p_limit integer)
returns table (
  job_id uuid,
  search_document_id uuid,
  entity_kind text,
  entity_id uuid,
  title text,
  body text,
  locale_terms text[]
)
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_limit integer := least(greatest(coalesce(p_limit, 64), 1), 64);
begin
  return query
  with picked as (
    select ej.id
    from public.embedding_jobs ej
    where ej.status = 'queued'
       or (
         ej.status = 'processing'
         and ej.updated_at < timezone('utc', now()) - interval '15 minutes'
       )
    order by ej.created_at asc
    limit v_limit
    for update skip locked
  ),
  claimed as (
    update public.embedding_jobs ej
    set
      status = 'processing',
      updated_at = timezone('utc', now())
    from picked p
    where ej.id = p.id
    returning ej.id, ej.search_document_id, ej.entity_kind, ej.entity_id
  )
  select
    c.id,
    c.search_document_id,
    c.entity_kind,
    c.entity_id,
    sd.title,
    sd.body,
    sd.locale_terms
  from claimed c
  join public.search_documents sd on sd.id = c.search_document_id;
end;
$$;

comment on function public.claim_embedding_jobs(integer) is
  'Claim up to 64 queued (or stale processing) embedding jobs for one internal tick.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.embedding_jobs enable row level security;
alter table public.embedding_jobs force row level security;

create policy embedding_jobs_admin_select
  on public.embedding_jobs
  for select
  to authenticated
  using (public.has_role('admin'));

create policy embedding_jobs_service_role_all
  on public.embedding_jobs
  for all
  to service_role
  using (true)
  with check (true);

comment on policy embedding_jobs_admin_select on public.embedding_jobs is
  'Admins may inspect embedding job queue including dead-letter rows.';
comment on policy embedding_jobs_service_role_all on public.embedding_jobs is
  'Internal API batch tick uses service_role to claim and update jobs.';

grant select on table public.embedding_jobs to authenticated;
grant select, insert, update, delete on table public.embedding_jobs to service_role;

grant execute on function public.embedding_enqueue_document(uuid, text, uuid) to service_role;
grant execute on function public.claim_embedding_jobs(integer) to service_role;
