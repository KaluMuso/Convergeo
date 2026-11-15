-- Events collaboration (flag `events_collaboration`, default OFF).
--
-- A vendor without organiser KYC proposes an event to run under a verified
-- organiser. The organiser approves, declines (with a reason) or asks for
-- changes; only an approved request can be published, and publishing creates
-- the event under the ORGANISER's verified account with the proposing vendor
-- recorded as co-host. Ticket revenue and payouts follow the existing organiser
-- flow; the proposed split is only recorded (integer basis points) for the
-- ledger to use later — payouts are OFF in the pilot.
--
--   * public.event_collab_organiser_prefs — organiser opt-in (Settings page).
--   * public.event_collab_requests        — the request (draft jsonb + checklist
--                                           jsonb + share bps), guarded state machine.
--   * public.event_collab_audit           — append-only transition log.
--   * public.event_revenue_splits         — co-host + share per published event
--                                           (kept off public.events so the public
--                                           read grant and organiser UPDATE grant
--                                           can never expose or rewrite the split).
--   * public.event_collab_transition()    — the ONLY way to change a request's
--                                           status (service_role execute only).
--
-- State machine: draft -> submitted -> changes_requested -> submitted ...
--                submitted -> approved | declined ; approved -> published.
-- A trigger rejects any status change that does not come through the function,
-- and freezes the proposal content once it leaves draft/changes_requested.
--
-- Notifications reuse the in-app notification writer
-- (private.enqueue_in_app_notification, migration 20261113130000): no outbox
-- row, no WhatsApp, no new i18n type — rows render the existing generic
-- "You have a new update." fallback and link to the request.
--
-- Additive only. Reversible — see the DOWN block at the end of this file.

-- ---------------------------------------------------------------------------
-- 1. Flag
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  (
    'events_collaboration',
    false,
    'Vendor event collaboration: a vendor without organiser KYC proposes an event to run '
    'under a verified, opted-in organiser (approve / decline / changes, then publish with '
    'the vendor as co-host). Default OFF.'
  )
on conflict (flag) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Organiser opt-in
-- ---------------------------------------------------------------------------

create table public.event_collab_organiser_prefs (
  vendor_id uuid primary key references public.vendors (id) on delete cascade,
  accepts_requests boolean not null default false,
  blurb text check (blurb is null or char_length(blurb) <= 280),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index event_collab_organiser_prefs_open_idx
  on public.event_collab_organiser_prefs (vendor_id)
  where accepts_requests;

create trigger event_collab_organiser_prefs_set_updated_at
  before update on public.event_collab_organiser_prefs
  for each row
  execute function public.set_updated_at();

comment on table public.event_collab_organiser_prefs is
  'Organiser opt-in to receive event collaboration requests. Written by the API '
  '(service role) after an organiser-eligibility check; the owner and admins may read.';

-- ---------------------------------------------------------------------------
-- 3. Requests
-- ---------------------------------------------------------------------------

create table public.event_collab_requests (
  id uuid primary key default gen_random_uuid(),
  proposer_vendor_id uuid not null references public.vendors (id) on delete restrict,
  organiser_vendor_id uuid not null references public.vendors (id) on delete restrict,
  status text not null default 'draft'
    check (status in (
      'draft', 'submitted', 'changes_requested', 'approved', 'declined', 'published'
    )),
  event_draft jsonb not null default '{}'::jsonb
    check (jsonb_typeof(event_draft) = 'object' and octet_length(event_draft::text) <= 16384),
  checklist jsonb not null default '{}'::jsonb
    check (jsonb_typeof(checklist) = 'object' and octet_length(checklist::text) <= 16384),
  readiness_pct smallint not null default 0 check (readiness_pct between 0 and 100),
  -- Co-host (proposer) share of ticket revenue, integer basis points (1% = 100).
  revenue_share_bps integer check (revenue_share_bps is null or revenue_share_bps between 0 and 10000),
  -- Latest organiser reason: decline reason or the changes they asked for.
  organiser_note text check (organiser_note is null or char_length(organiser_note) <= 1000),
  event_id uuid references public.events (id) on delete set null,
  submitted_at timestamptz,
  decided_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint event_collab_requests_parties_differ check (proposer_vendor_id <> organiser_vendor_id),
  constraint event_collab_requests_published_has_event
    check (status <> 'published' or event_id is not null),
  constraint event_collab_requests_submitted_has_share
    check (status = 'draft' or revenue_share_bps is not null)
);

create index event_collab_requests_organiser_idx
  on public.event_collab_requests (organiser_vendor_id, status, updated_at desc);
create index event_collab_requests_proposer_idx
  on public.event_collab_requests (proposer_vendor_id, updated_at desc);
create unique index event_collab_requests_event_uidx
  on public.event_collab_requests (event_id) where event_id is not null;

create trigger event_collab_requests_set_updated_at
  before update on public.event_collab_requests
  for each row
  execute function public.set_updated_at();

comment on table public.event_collab_requests is
  'Vendor-to-organiser event collaboration requests. Status changes ONLY via '
  'public.event_collab_transition(); content is editable only in draft/changes_requested.';

create table public.event_collab_audit (
  id bigint generated always as identity primary key,
  request_id uuid not null references public.event_collab_requests (id) on delete restrict,
  actor_user_id uuid references auth.users (id) on delete set null,
  actor_role text not null check (actor_role in ('proposer', 'organiser', 'system')),
  action text not null
    check (action in ('create', 'submit', 'approve', 'decline', 'request_changes', 'publish')),
  from_status text,
  to_status text not null,
  reason text check (reason is null or char_length(reason) <= 1000),
  created_at timestamptz not null default timezone('utc', now())
);

create index event_collab_audit_request_idx
  on public.event_collab_audit (request_id, id);

comment on table public.event_collab_audit is
  'Append-only transition log for event_collab_requests (UPDATE/DELETE rejected by trigger).';

create table public.event_revenue_splits (
  event_id uuid primary key references public.events (id) on delete cascade,
  collaboration_request_id uuid not null unique
    references public.event_collab_requests (id) on delete restrict,
  organiser_vendor_id uuid not null references public.vendors (id) on delete restrict,
  co_host_vendor_id uuid not null references public.vendors (id) on delete restrict,
  -- Co-host share of ticket revenue in integer basis points. RECORDED ONLY:
  -- payouts are OFF in the pilot; the ledger reads this later. The organiser
  -- stays accountable for ticket revenue and payouts.
  co_host_share_bps integer not null check (co_host_share_bps between 0 and 10000),
  created_at timestamptz not null default timezone('utc', now()),
  constraint event_revenue_splits_parties_differ check (organiser_vendor_id <> co_host_vendor_id)
);

create index event_revenue_splits_co_host_idx on public.event_revenue_splits (co_host_vendor_id);

comment on table public.event_revenue_splits is
  'Co-host revenue split recorded when a collaboration event is published. Immutable; '
  'not exposed publicly (events carries no split columns).';

-- ---------------------------------------------------------------------------
-- 4. Guards
-- ---------------------------------------------------------------------------

create or replace function private.event_collab_requests_guard()
returns trigger
language plpgsql
set search_path = public, private
as $$
begin
  if tg_op = 'INSERT' then
    if new.status is distinct from 'draft' then
      raise exception 'event collaboration requests are created as draft'
        using errcode = '42501';
    end if;
    return new;
  end if;

  if new.id is distinct from old.id
     or new.proposer_vendor_id is distinct from old.proposer_vendor_id
     or new.organiser_vendor_id is distinct from old.organiser_vendor_id then
    raise exception 'event collaboration parties are immutable' using errcode = '42501';
  end if;

  if new.status is distinct from old.status
     and coalesce(current_setting('app.event_collab_transition', true), '') <> 'on' then
    raise exception 'event collaboration status changes only through event_collab_transition()'
      using errcode = '42501';
  end if;

  if new.status is not distinct from old.status
     and old.status not in ('draft', 'changes_requested')
     and (new.event_draft is distinct from old.event_draft
          or new.checklist is distinct from old.checklist
          or new.revenue_share_bps is distinct from old.revenue_share_bps
          or new.readiness_pct is distinct from old.readiness_pct) then
    raise exception 'event collaboration proposal is frozen once submitted'
      using errcode = '55000';
  end if;

  return new;
end;
$$;

revoke all on function private.event_collab_requests_guard() from public, anon, authenticated;

create trigger event_collab_requests_guard
  before insert or update on public.event_collab_requests
  for each row
  execute function private.event_collab_requests_guard();

create or replace function private.event_collab_append_only()
returns trigger
language plpgsql
set search_path = public, private
as $$
begin
  raise exception '% rows are append-only', tg_table_name using errcode = '42501';
end;
$$;

revoke all on function private.event_collab_append_only() from public, anon, authenticated;

create trigger event_collab_audit_append_only
  before update or delete on public.event_collab_audit
  for each row
  execute function private.event_collab_append_only();

create trigger event_revenue_splits_immutable
  before update on public.event_revenue_splits
  for each row
  execute function private.event_collab_append_only();

-- ---------------------------------------------------------------------------
-- 5. RLS (FORCE on every table)
-- ---------------------------------------------------------------------------

alter table public.event_collab_organiser_prefs enable row level security;
alter table public.event_collab_organiser_prefs force row level security;
alter table public.event_collab_requests enable row level security;
alter table public.event_collab_requests force row level security;
alter table public.event_collab_audit enable row level security;
alter table public.event_collab_audit force row level security;
alter table public.event_revenue_splits enable row level security;
alter table public.event_revenue_splits force row level security;

revoke all on public.event_collab_organiser_prefs from public, anon, authenticated;
revoke all on public.event_collab_requests from public, anon, authenticated;
revoke all on public.event_collab_audit from public, anon, authenticated;
revoke all on public.event_revenue_splits from public, anon, authenticated;

-- Clients (parties and admins) read; every write goes through the API (service
-- role). Admin access is read-only (D1, 20261115140100: no admin write policies).
grant select on public.event_collab_organiser_prefs to authenticated;
grant select on public.event_collab_requests to authenticated;
grant select on public.event_collab_audit to authenticated;
grant select on public.event_revenue_splits to authenticated;
grant all on public.event_collab_organiser_prefs to service_role;
grant all on public.event_collab_requests to service_role;
grant all on public.event_collab_audit to service_role;
grant all on public.event_revenue_splits to service_role;

create policy event_collab_prefs_owner_select
  on public.event_collab_organiser_prefs
  for select to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = event_collab_organiser_prefs.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_collab_prefs_admin_select
  on public.event_collab_organiser_prefs
  for select to authenticated
  using (public.has_role('admin'));

-- The proposing vendor and the chosen organiser can read the request.
create policy event_collab_requests_party_select
  on public.event_collab_requests
  for select to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id in (
              event_collab_requests.proposer_vendor_id,
              event_collab_requests.organiser_vendor_id
            )
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_collab_requests_admin_select
  on public.event_collab_requests
  for select to authenticated
  using (public.has_role('admin'));

create policy event_collab_audit_party_select
  on public.event_collab_audit
  for select to authenticated
  using (
    exists (
      select 1
      from public.event_collab_requests r
      join public.vendors v on v.id in (r.proposer_vendor_id, r.organiser_vendor_id)
      where r.id = event_collab_audit.request_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_collab_audit_admin_select
  on public.event_collab_audit
  for select to authenticated
  using (public.has_role('admin'));

create policy event_revenue_splits_party_select
  on public.event_revenue_splits
  for select to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id in (
              event_revenue_splits.organiser_vendor_id,
              event_revenue_splits.co_host_vendor_id
            )
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy event_revenue_splits_admin_select
  on public.event_revenue_splits
  for select to authenticated
  using (public.has_role('admin'));

-- ---------------------------------------------------------------------------
-- 6. The guarded state machine
-- ---------------------------------------------------------------------------

create or replace function public.event_collab_transition(
  p_request_id uuid,
  p_actor_user_id uuid,
  p_action text,
  p_reason text default null,
  p_event_slug text default null
)
returns public.event_collab_requests
language plpgsql
security definer
set search_path = public, private
as $$
declare
  r public.event_collab_requests%rowtype;
  v_proposer_owner uuid;
  v_organiser_owner uuid;
  v_organiser_status text;
  v_role text;
  v_need_role text;
  v_from text;
  v_to text;
  v_reason text := nullif(btrim(coalesce(p_reason, '')), '');
  v_event_id uuid;
  v_event jsonb;
  v_chk jsonb;
  v_instance_id uuid;
  v_tier jsonb;
  v_recipient uuid;
begin
  if p_action not in ('submit', 'approve', 'decline', 'request_changes', 'publish') then
    raise exception 'unknown event collaboration action %', p_action using errcode = '22023';
  end if;

  select * into r from public.event_collab_requests where id = p_request_id for update;
  if not found then
    raise exception 'event collaboration request not found' using errcode = 'P0002';
  end if;

  select owner_user_id into v_proposer_owner from public.vendors where id = r.proposer_vendor_id;
  select owner_user_id, status into v_organiser_owner, v_organiser_status
    from public.vendors where id = r.organiser_vendor_id;

  v_role := case
    when p_actor_user_id is not null and p_actor_user_id = v_organiser_owner then 'organiser'
    when p_actor_user_id is not null and p_actor_user_id = v_proposer_owner then 'proposer'
    else null
  end;
  if v_role is null then
    raise exception 'actor is not a party to this request' using errcode = '42501';
  end if;

  v_need_role := case p_action when 'submit' then 'proposer' else 'organiser' end;
  if v_role <> v_need_role then
    raise exception '% requires the % of the request', p_action, v_need_role
      using errcode = '42501';
  end if;

  v_from := r.status;
  v_to := case p_action
    when 'submit' then 'submitted'
    when 'approve' then 'approved'
    when 'decline' then 'declined'
    when 'request_changes' then 'changes_requested'
    when 'publish' then 'published'
  end;

  if not (
       (p_action = 'submit' and v_from in ('draft', 'changes_requested'))
    or (p_action in ('approve', 'decline', 'request_changes') and v_from = 'submitted')
    or (p_action = 'publish' and v_from = 'approved')
  ) then
    raise exception 'cannot % a request that is %', p_action, v_from using errcode = '55000';
  end if;

  if p_action in ('decline', 'request_changes') and (v_reason is null or char_length(v_reason) < 3) then
    raise exception '% needs a reason', p_action using errcode = '22023';
  end if;

  if p_action = 'submit'
     and (r.revenue_share_bps is null
          or coalesce(r.event_draft ->> 'title', '') = ''
          or r.checklist = '{}'::jsonb) then
    raise exception 'event draft and checklist are incomplete' using errcode = '22023';
  end if;

  perform set_config('app.event_collab_transition', 'on', true);

  if p_action = 'publish' then
    if v_organiser_status is distinct from 'active' then
      raise exception 'organiser account is not active' using errcode = '55000';
    end if;
    if p_event_slug is null or p_event_slug !~ '^[a-z0-9][a-z0-9-]{0,99}$' then
      raise exception 'a valid event slug is required' using errcode = '22023';
    end if;
    v_event := r.event_draft;
    v_chk := r.checklist;

    insert into public.events (
      organiser_vendor_id, title, slug, description, venue, lat, lng, landmark,
      category_slug, city, status
    ) values (
      r.organiser_vendor_id,
      v_event ->> 'title',
      p_event_slug,
      nullif(v_event ->> 'description', ''),
      nullif(v_chk #>> '{venue,name}', ''),
      (v_chk #>> '{venue,lat}')::double precision,
      (v_chk #>> '{venue,lng}')::double precision,
      nullif(v_chk #>> '{venue,landmark}', ''),
      nullif(v_event ->> 'category', ''),
      nullif(v_event ->> 'city', ''),
      'draft'
    )
    returning id into v_event_id;

    insert into public.event_instances (event_id, starts_at, ends_at, capacity)
    values (
      v_event_id,
      (v_chk #>> '{schedule,starts_at}')::timestamptz,
      (v_chk #>> '{schedule,ends_at}')::timestamptz,
      (v_chk #>> '{capacity,capacity}')::int
    )
    returning id into v_instance_id;

    for v_tier in select * from jsonb_array_elements(coalesce(v_chk -> 'tiers', '[]'::jsonb))
    loop
      insert into public.ticket_types (event_id, kind, name, price_ngwee, qty_cap)
      values (
        v_event_id,
        case when (v_tier ->> 'price_ngwee')::bigint = 0 then 'free_rsvp' else 'tier' end,
        v_tier ->> 'name',
        (v_tier ->> 'price_ngwee')::bigint,
        nullif(v_tier ->> 'qty_cap', '')::int
      );
    end loop;

    update public.events set status = 'published' where id = v_event_id;

    insert into public.event_revenue_splits (
      event_id, collaboration_request_id, organiser_vendor_id, co_host_vendor_id,
      co_host_share_bps
    ) values (
      v_event_id, r.id, r.organiser_vendor_id, r.proposer_vendor_id, r.revenue_share_bps
    );
  end if;

  update public.event_collab_requests set
    status = v_to,
    organiser_note = case
      when p_action in ('decline', 'request_changes') then left(v_reason, 1000)
      else organiser_note
    end,
    submitted_at = case when p_action = 'submit' then timezone('utc', now()) else submitted_at end,
    decided_at = case
      when p_action in ('approve', 'decline', 'request_changes') then timezone('utc', now())
      else decided_at
    end,
    published_at = case when p_action = 'publish' then timezone('utc', now()) else published_at end,
    event_id = case when p_action = 'publish' then v_event_id else event_id end
  where id = r.id
  returning * into r;

  perform set_config('app.event_collab_transition', 'off', true);

  insert into public.event_collab_audit (
    request_id, actor_user_id, actor_role, action, from_status, to_status, reason
  ) values (
    r.id, p_actor_user_id, v_role, p_action, v_from, v_to, left(v_reason, 1000)
  );

  -- In-app notification to the other party (existing writer; failures never
  -- roll back the transition).
  begin
    v_recipient := case when p_action = 'submit' then v_organiser_owner else v_proposer_owner end;
    perform private.enqueue_in_app_notification(
      v_recipient, 'vendor', 'event_collab_update', '{}'::jsonb,
      '/events/collaborate/' || r.id::text,
      'event_collab_update:' || r.id::text || ':' || p_action || ':'
        || to_char(clock_timestamp(), 'YYYYMMDDHH24MISSUS')
    );
  exception when others then
    raise warning 'event_collab notification skipped (sqlstate %): %', sqlstate, sqlerrm;
  end;

  return r;
end;
$$;

revoke all on function public.event_collab_transition(uuid, uuid, text, text, text)
  from public, anon, authenticated;
grant execute on function public.event_collab_transition(uuid, uuid, text, text, text)
  to service_role;

-- Draft creation is audited too (kept out of the state machine: a draft has no
-- from-state). Service role only.
create or replace function public.event_collab_record_create(
  p_request_id uuid,
  p_actor_user_id uuid
)
returns void
language sql
security definer
set search_path = public, private
as $$
  insert into public.event_collab_audit (
    request_id, actor_user_id, actor_role, action, from_status, to_status
  ) values (p_request_id, p_actor_user_id, 'proposer', 'create', null, 'draft');
$$;

revoke all on function public.event_collab_record_create(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.event_collab_record_create(uuid, uuid) to service_role;

-- ---------------------------------------------------------------------------
-- DOWN (manual; run in one transaction to reverse this migration)
-- ---------------------------------------------------------------------------
-- drop function if exists public.event_collab_record_create(uuid, uuid);
-- drop function if exists public.event_collab_transition(uuid, uuid, text, text, text);
-- drop table if exists public.event_revenue_splits;
-- drop table if exists public.event_collab_audit;
-- drop table if exists public.event_collab_requests;
-- drop table if exists public.event_collab_organiser_prefs;
-- drop function if exists private.event_collab_append_only();
-- drop function if exists private.event_collab_requests_guard();
-- delete from public.feature_flags where flag = 'events_collaboration';
