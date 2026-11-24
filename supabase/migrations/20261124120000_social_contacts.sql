-- T8 part 1: social contacts ("add people", WeChat-style). Feature flag
-- `social_contacts`, default OFF. Spec: prompts/agents/T8-social-contacts-spec.md.
-- Database + RLS only; the FastAPI endpoints and the customer UI come next.
--
--   user_handles        Vergeo ID (@handle), lowercase, unique, 30-day edit cooldown
--   contact_requests    pending / accepted / ignored / expired; one pending per pair
--   contacts            accepted pairs, stored ordered (user_a < user_b)
--   contact_blocks      blocker -> blocked; the EFFECT is two-way
--   chat_threads        one 1:1 thread per ordered pair
--   chat_messages       text or share_card (product / service / event), no media
--   phone_discovery     opt-in, peppered SHA-256 of the E.164 number, never raw
--   profiles.contact_requests_from   'everyone' (default) | 'no_one'
--
-- Security model
--   * RLS ENABLE + FORCE on every new table. Clients get SELECT only, and only
--     on rows where they are a party (handles / blocks / phone row: the owner).
--     A pair with a block in either direction is hidden from both parties
--     (threads, messages, requests).
--   * No client INSERT / UPDATE / DELETE grant on any new table. Every write
--     goes through a SECURITY DEFINER function below (search_path pinned,
--     EXECUTE revoked from public/anon). The actor is auth.uid() for a user
--     JWT; a service-role caller (the API) passes p_actor instead. A user JWT
--     can never act for someone else (p_actor must match or be null).
--   * Handle -> card lookup goes through lookup_handle_card(), which returns
--     nothing when either side has blocked the other.
--   * Phone discovery and the phone-hash write are service-role only: the
--     hash uses a server pepper, so only the API can compute it, and a client
--     must never claim a hash for a number it has not verified.
--
-- Rate limits are enforced in the database from the tables themselves
-- (30 requests per user per rolling 24 h; 20 messages per sender per thread per
-- rolling minute). public.bump_rate_counter / rate_counters cannot be used here:
-- the rate_counters guard trigger admits only service_role or a direct
-- postgres session, so a user-JWT call of these functions would always fail.
-- The scopes registered in section 9 are for the API's own per-endpoint
-- bump_rate_counter limits (defence in depth on top of these).
--
-- Error contract (raised as SQLSTATE P0001 unless noted; the API maps them):
--   social:disabled            flag off
--   social:unauthenticated     no actor (42501)      social:actor_mismatch (42501)
--   social:handle_invalid      social:handle_taken    social:handle_cooldown
--   social:unavailable         unknown handle, or the recipient blocked you
--   social:not_accepting       recipient set 'no_one'
--   social:you_blocked         you blocked the recipient (unblock first)
--   social:self                social:already_contact social:duplicate
--   social:note_too_long       social:rate_limited
--   social:not_found           request / thread missing or not yours
--   social:not_pending         social:invalid_action
--   social:not_contact         no contact, or a block in either direction
--   social:message_invalid     social:too_many_hashes
--
-- Additive only. Reversible (manual; safe while the flag has never been on,
-- otherwise export the tables first: they hold users' chats):
--   drop function if exists public.my_contact_requests();
--   drop function if exists public.expire_contact_requests();
--   drop function if exists public.set_phone_discovery(uuid, text, boolean);
--   drop function if exists public.discover_by_phone_hashes(text[], uuid);
--   drop function if exists public.send_chat_message(uuid, text, text, jsonb, uuid);
--   drop function if exists public.unblock_user(uuid, uuid);
--   drop function if exists public.block_user(uuid, uuid);
--   drop function if exists public.remove_contact(uuid, uuid);
--   drop function if exists public.respond_contact_request(uuid, text, uuid);
--   drop function if exists public.send_contact_request(text, text, uuid);
--   drop function if exists public.lookup_handle_card(text, uuid);
--   drop function if exists public.set_my_handle(text, uuid);
--   drop function if exists private.social_accept_request(uuid);
--   drop function if exists private.social_blocked(uuid, uuid);
--   drop function if exists private.social_actor(uuid);
--   drop function if exists private.social_enabled();
--   drop table if exists public.phone_discovery;
--   drop table if exists public.chat_messages;
--   drop table if exists public.chat_threads;
--   drop table if exists public.contact_blocks;
--   drop table if exists public.contacts;
--   drop table if exists public.contact_requests;
--   drop table if exists public.user_handles;
--   drop function if exists private.user_handles_guard();
--   alter table public.profiles drop column if exists contact_requests_from;
--   delete from public.feature_flags where flag = 'social_contacts';
--   delete from private.rate_counter_scope_manifest where scope in (
--     'social_request_user', 'social_message_user', 'social_discover_user',
--     'social_lookup_user');
--   -- then rebuild rate_counters_scope_check from the manifest (section 9),
--   -- only once no rate_counters row uses those scopes.

-- ---------------------------------------------------------------------------
-- 1. Flag
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  ('social_contacts', false,
   'Social contacts (T8): @handles, contact requests, blocks and 1:1 chat with share cards.')
on conflict (flag) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Privacy setting on profiles (owner-updatable through the existing
--    profiles_owner_update policy; the check constraint bounds the values)
-- ---------------------------------------------------------------------------

alter table public.profiles
  add column if not exists contact_requests_from text not null default 'everyone';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname = 'profiles_contact_requests_from_check'
  ) then
    alter table public.profiles
      add constraint profiles_contact_requests_from_check
      check (contact_requests_from in ('everyone', 'no_one'));
  end if;
end;
$$;

comment on column public.profiles.contact_requests_from is
  'T8: who can send this user contact requests: everyone (default) or no_one.';

-- ---------------------------------------------------------------------------
-- 3. Tables
-- ---------------------------------------------------------------------------

-- Handles are stored lowercase (the format check admits only [a-z0-9_.]), so
-- the plain unique constraint is case-insensitive by construction; callers
-- pass any case and set_my_handle / lookups normalise with lower().
create table if not exists public.user_handles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  handle text not null,
  changed_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  constraint user_handles_handle_format check (handle ~ '^[a-z0-9_.]{3,24}$'),
  constraint user_handles_handle_key unique (handle)
);

comment on table public.user_handles is
  'T8 Vergeo ID (@handle). Lowercase, unique, editable once per 30 days (trigger). Owner reads own row; others resolve a handle only via lookup_handle_card().';

create table if not exists public.contact_requests (
  id uuid primary key default gen_random_uuid(),
  from_user uuid not null references auth.users (id) on delete cascade,
  to_user uuid not null references auth.users (id) on delete cascade,
  note text,
  status text not null default 'pending',
  created_at timestamptz not null default timezone('utc', now()),
  decided_at timestamptz,
  constraint contact_requests_not_self check (from_user <> to_user),
  constraint contact_requests_note_length check (note is null or char_length(note) <= 80),
  constraint contact_requests_status_check
    check (status in ('pending', 'accepted', 'ignored', 'expired')),
  constraint contact_requests_decided_check check ((status = 'pending') = (decided_at is null))
);

-- One pending request per unordered pair (A->B and B->A cannot both be pending;
-- send_contact_request turns a crossing request into an accept).
create unique index if not exists contact_requests_pending_pair_uidx
  on public.contact_requests (least(from_user, to_user), greatest(from_user, to_user))
  where status = 'pending';
create index if not exists contact_requests_to_status_idx
  on public.contact_requests (to_user, status, created_at desc);
create index if not exists contact_requests_from_created_idx
  on public.contact_requests (from_user, created_at desc);
create index if not exists contact_requests_pending_created_idx
  on public.contact_requests (created_at) where status = 'pending';

comment on table public.contact_requests is
  'T8 contact requests. Visible to the two parties (hidden while either blocks the other). Written only by send_/respond_contact_request, block_user and expire_contact_requests.';

create table if not exists public.contacts (
  user_a uuid not null references auth.users (id) on delete cascade,
  user_b uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (user_a, user_b),
  constraint contacts_ordered_pair check (user_a < user_b)
);

create index if not exists contacts_user_b_idx on public.contacts (user_b);

comment on table public.contacts is
  'T8 accepted contacts, one row per ordered pair (user_a < user_b). Written only by the social functions.';

create table if not exists public.contact_blocks (
  blocker uuid not null references auth.users (id) on delete cascade,
  blocked uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (blocker, blocked),
  constraint contact_blocks_not_self check (blocker <> blocked)
);

create index if not exists contact_blocks_blocked_idx on public.contact_blocks (blocked);

comment on table public.contact_blocks is
  'T8 blocks. Only the blocker can see the row; the effect (no lookup, requests or messages) is two-way.';

create table if not exists public.chat_threads (
  id uuid primary key default gen_random_uuid(),
  user_a uuid not null references auth.users (id) on delete cascade,
  user_b uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  last_message_at timestamptz,
  constraint chat_threads_ordered_pair check (user_a < user_b),
  constraint chat_threads_pair_key unique (user_a, user_b)
);

create index if not exists chat_threads_user_b_idx on public.chat_threads (user_b);
create index if not exists chat_threads_user_a_last_idx
  on public.chat_threads (user_a, last_message_at desc nulls last);

comment on table public.chat_threads is
  'T8 1:1 threads, one per ordered pair. Created on accept; kept after remove/block (hidden while blocked).';

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.chat_threads (id) on delete cascade,
  sender uuid not null references auth.users (id) on delete cascade,
  kind text not null,
  body text,
  card jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint chat_messages_kind_check check (kind in ('text', 'share_card')),
  constraint chat_messages_body_length
    check (body is null or char_length(body) between 1 and 2000),
  constraint chat_messages_text_shape
    check (kind <> 'text' or (body is not null and card is null)),
  -- share_card: {"type": product|service|event, "id": "<listing id>", ...}
  -- small object only; the client renders it from the live listing.
  constraint chat_messages_card_shape check (
    (kind = 'share_card') = (card is not null)
    and (
      card is null
      or (
        jsonb_typeof(card) = 'object'
        and card ->> 'type' in ('product', 'service', 'event')
        and coalesce(card ->> 'id', '') ~ '^[-._A-Za-z0-9]{1,64}$'
        and octet_length(card::text) <= 2048
      )
    )
  )
);

create index if not exists chat_messages_thread_created_idx
  on public.chat_messages (thread_id, created_at desc, id desc);
create index if not exists chat_messages_thread_sender_created_idx
  on public.chat_messages (thread_id, sender, created_at desc);

comment on table public.chat_messages is
  'T8 1:1 messages (text or share_card, no media). Visible to thread parties; written only by send_chat_message().';

create table if not exists public.phone_discovery (
  user_id uuid primary key references auth.users (id) on delete cascade,
  phone_hash text not null,
  enabled boolean not null default false,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint phone_discovery_hash_format check (phone_hash ~ '^[0-9a-f]{64}$')
);

create index if not exists phone_discovery_hash_enabled_idx
  on public.phone_discovery (phone_hash) where enabled;

comment on table public.phone_discovery is
  'T8 opt-in phone discovery. phone_hash = hex SHA-256 of E.164 with a server pepper (never the raw number). Written by the API (service role) only.';

-- ---------------------------------------------------------------------------
-- 4. Handle guard: 30-day edit cooldown, user_id immutable
-- ---------------------------------------------------------------------------

create or replace function private.user_handles_guard()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if tg_op = 'INSERT' then
    new.changed_at := timezone('utc', now());
    new.created_at := timezone('utc', now());
    return new;
  end if;

  if new.user_id is distinct from old.user_id then
    raise exception 'social:handle_owner_immutable' using errcode = '42501';
  end if;
  new.created_at := old.created_at;

  if new.handle is distinct from old.handle then
    if old.changed_at > timezone('utc', now()) - interval '30 days' then
      raise exception 'social:handle_cooldown';
    end if;
    new.changed_at := timezone('utc', now());
  elsif session_user not in ('postgres', 'supabase_admin') then
    -- Only a trusted direct session (support / tests) may reset the cooldown.
    new.changed_at := old.changed_at;
  end if;
  return new;
end;
$$;

drop trigger if exists user_handles_guard on public.user_handles;
create trigger user_handles_guard
  before insert or update on public.user_handles
  for each row
  execute function private.user_handles_guard();

revoke all on function private.user_handles_guard() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 5. Private helpers
-- ---------------------------------------------------------------------------

create or replace function private.social_enabled()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select coalesce(
    (select enabled from public.feature_flags where flag = 'social_contacts'),
    false
  );
$$;

-- The acting user: auth.uid() for a user JWT (p_actor must be null or equal);
-- p_actor for the service role or a trusted direct session.
create or replace function private.social_actor(p_actor uuid)
returns uuid
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is not null then
    if p_actor is not null and p_actor <> v_uid then
      raise exception 'social:actor_mismatch' using errcode = '42501';
    end if;
    return v_uid;
  end if;
  if p_actor is not null
     and (session_user in ('postgres', 'supabase_admin')
          or coalesce(auth.role(), '') = 'service_role') then
    return p_actor;
  end if;
  raise exception 'social:unauthenticated' using errcode = '42501';
end;
$$;

-- True when either user has blocked the other. Used by the RLS policies, so
-- authenticated may execute it (the private schema is not exposed by PostgREST,
-- and a caller only ever learns about pairs it is a party to through RLS).
create or replace function private.social_blocked(p_a uuid, p_b uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1 from public.contact_blocks b
    where (b.blocker = p_a and b.blocked = p_b)
       or (b.blocker = p_b and b.blocked = p_a)
  );
$$;

-- Accept a locked pending request: contact row + chat thread. Returns thread id.
create or replace function private.social_accept_request(p_request_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_req public.contact_requests%rowtype;
  v_a uuid;
  v_b uuid;
  v_thread uuid;
begin
  select * into v_req from public.contact_requests where id = p_request_id for update;
  if not found or v_req.status <> 'pending' then
    raise exception 'social:not_pending';
  end if;
  if private.social_blocked(v_req.from_user, v_req.to_user) then
    raise exception 'social:not_contact';
  end if;

  v_a := least(v_req.from_user, v_req.to_user);
  v_b := greatest(v_req.from_user, v_req.to_user);

  update public.contact_requests
     set status = 'accepted', decided_at = timezone('utc', now())
   where id = p_request_id;

  insert into public.contacts (user_a, user_b) values (v_a, v_b)
  on conflict (user_a, user_b) do nothing;

  insert into public.chat_threads (user_a, user_b) values (v_a, v_b)
  on conflict (user_a, user_b) do nothing;

  select id into v_thread from public.chat_threads where user_a = v_a and user_b = v_b;
  return v_thread;
end;
$$;

revoke all on function private.social_enabled() from public, anon, authenticated;
revoke all on function private.social_actor(uuid) from public, anon, authenticated;
revoke all on function private.social_blocked(uuid, uuid) from public, anon, authenticated;
revoke all on function private.social_accept_request(uuid) from public, anon, authenticated;
grant execute on function private.social_blocked(uuid, uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 6. RLS
-- ---------------------------------------------------------------------------

alter table public.user_handles enable row level security;
alter table public.user_handles force row level security;
alter table public.contact_requests enable row level security;
alter table public.contact_requests force row level security;
alter table public.contacts enable row level security;
alter table public.contacts force row level security;
alter table public.contact_blocks enable row level security;
alter table public.contact_blocks force row level security;
alter table public.chat_threads enable row level security;
alter table public.chat_threads force row level security;
alter table public.chat_messages enable row level security;
alter table public.chat_messages force row level security;
alter table public.phone_discovery enable row level security;
alter table public.phone_discovery force row level security;

drop policy if exists user_handles_select_own on public.user_handles;
create policy user_handles_select_own on public.user_handles
  for select to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists contact_requests_select_party on public.contact_requests;
-- Ignoring is silent: the sender never reads an 'ignored' row directly. Their
-- outgoing list comes from my_contact_requests(), which shows it as pending.
create policy contact_requests_select_party on public.contact_requests
  for select to authenticated
  using (
    ((select auth.uid()) = to_user
      or ((select auth.uid()) = from_user and status <> 'ignored'))
    and not private.social_blocked(from_user, to_user)
  );

drop policy if exists contacts_select_party on public.contacts;
create policy contacts_select_party on public.contacts
  for select to authenticated
  using ((select auth.uid()) in (user_a, user_b));

drop policy if exists contact_blocks_select_blocker on public.contact_blocks;
create policy contact_blocks_select_blocker on public.contact_blocks
  for select to authenticated
  using (blocker = (select auth.uid()));

drop policy if exists chat_threads_select_party on public.chat_threads;
create policy chat_threads_select_party on public.chat_threads
  for select to authenticated
  using (
    (select auth.uid()) in (user_a, user_b)
    and not private.social_blocked(user_a, user_b)
  );

-- The subquery runs under chat_threads RLS, so it already means
-- "a thread I am a party to and that is not blocked".
drop policy if exists chat_messages_select_party on public.chat_messages;
create policy chat_messages_select_party on public.chat_messages
  for select to authenticated
  using (exists (select 1 from public.chat_threads t where t.id = chat_messages.thread_id));

drop policy if exists phone_discovery_select_own on public.phone_discovery;
create policy phone_discovery_select_own on public.phone_discovery
  for select to authenticated
  using (user_id = (select auth.uid()));

revoke all on public.user_handles from public, anon, authenticated;
revoke all on public.contact_requests from public, anon, authenticated;
revoke all on public.contacts from public, anon, authenticated;
revoke all on public.contact_blocks from public, anon, authenticated;
revoke all on public.chat_threads from public, anon, authenticated;
revoke all on public.chat_messages from public, anon, authenticated;
revoke all on public.phone_discovery from public, anon, authenticated;

grant select on public.user_handles to authenticated, service_role;
grant select on public.contact_requests to authenticated, service_role;
grant select on public.contacts to authenticated, service_role;
grant select on public.contact_blocks to authenticated, service_role;
grant select on public.chat_threads to authenticated, service_role;
grant select on public.chat_messages to authenticated, service_role;
grant select on public.phone_discovery to authenticated;
grant select, insert, update, delete on public.phone_discovery to service_role;

-- ---------------------------------------------------------------------------
-- 7. Client-callable functions (user JWT or service role + p_actor)
-- ---------------------------------------------------------------------------

create or replace function public.set_my_handle(p_handle text, p_actor uuid default null)
returns text
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
  v_handle text := lower(btrim(ltrim(btrim(coalesce(p_handle, '')), '@')));
begin
  if not private.social_enabled() then
    raise exception 'social:disabled';
  end if;
  if v_handle !~ '^[a-z0-9_.]{3,24}$'
     or v_handle in ('admin', 'support', 'vergeo', 'vergeo5', 'convergeo', 'help',
                     'system', 'moderator', 'official', 'root') then
    raise exception 'social:handle_invalid';
  end if;

  begin
    insert into public.user_handles (user_id, handle) values (v_actor, v_handle)
    on conflict (user_id) do update
      set handle = excluded.handle
      where public.user_handles.handle is distinct from excluded.handle;
  exception when unique_violation then
    raise exception 'social:handle_taken';
  end;
  return v_handle;
end;
$$;

comment on function public.set_my_handle(text, uuid) is
  'T8: claim or change the caller''s @handle (lowercased; 30-day cooldown on change).';

create or replace function public.lookup_handle_card(p_handle text, p_actor uuid default null)
returns table (user_id uuid, handle text, display_name text, is_contact boolean)
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
  v_handle text := lower(btrim(ltrim(btrim(coalesce(p_handle, '')), '@')));
begin
  if not private.social_enabled() then
    raise exception 'social:disabled';
  end if;
  return query
    select h.user_id, h.handle, p.display_name,
           exists (
             select 1 from public.contacts c
             where c.user_a = least(v_actor, h.user_id)
               and c.user_b = greatest(v_actor, h.user_id)
           )
    from public.user_handles h
    join public.profiles p on p.id = h.user_id and p.deleted_at is null
    where h.handle = v_handle
      and not private.social_blocked(v_actor, h.user_id);
end;
$$;

comment on function public.lookup_handle_card(text, uuid) is
  'T8: @handle -> minimal public card. Empty when unknown, deleted, or a block exists either way.';

create or replace function public.send_contact_request(
  p_to_handle text,
  p_note text default null,
  p_actor uuid default null
)
returns table (request_id uuid, status text)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
  v_handle text := lower(btrim(ltrim(btrim(coalesce(p_to_handle, '')), '@')));
  v_note text := nullif(btrim(coalesce(p_note, '')), '');
  v_to uuid;
  v_setting text;
  v_reverse uuid;
  v_id uuid;
begin
  if not private.social_enabled() then
    raise exception 'social:disabled';
  end if;
  if v_note is not null and char_length(v_note) > 80 then
    raise exception 'social:note_too_long';
  end if;

  select h.user_id, p.contact_requests_from into v_to, v_setting
  from public.user_handles h
  join public.profiles p on p.id = h.user_id and p.deleted_at is null
  where h.handle = v_handle;
  if v_to is null then
    raise exception 'social:unavailable';
  end if;
  if v_to = v_actor then
    raise exception 'social:self';
  end if;

  -- Serialise concurrent sends for this pair (the pending index is the backstop).
  perform pg_advisory_xact_lock(
    hashtextextended('social_pair:' || least(v_actor, v_to)::text || greatest(v_actor, v_to)::text, 0)
  );

  if exists (select 1 from public.contact_blocks where blocker = v_actor and blocked = v_to) then
    raise exception 'social:you_blocked';
  end if;
  if exists (select 1 from public.contact_blocks where blocker = v_to and blocked = v_actor) then
    raise exception 'social:unavailable';
  end if;
  if exists (
    select 1 from public.contacts
    where user_a = least(v_actor, v_to) and user_b = greatest(v_actor, v_to)
  ) then
    raise exception 'social:already_contact';
  end if;

  -- A crossing request (they already asked me) is an accept, whatever my setting.
  select r.id into v_reverse from public.contact_requests r
  where r.from_user = v_to and r.to_user = v_actor and r.status = 'pending'
  for update;
  if v_reverse is not null then
    perform private.social_accept_request(v_reverse);
    request_id := v_reverse;
    status := 'accepted';
    return next;
    return;
  end if;

  if v_setting = 'no_one' then
    raise exception 'social:not_accepting';
  end if;

  -- Pending, or silently ignored in the last 30 days: the sender sees the same
  -- "already requested" answer either way (ignore stays silent).
  if exists (
    select 1 from public.contact_requests r
    where r.from_user = v_actor and r.to_user = v_to
      and (r.status = 'pending'
           or (r.status = 'ignored' and r.decided_at > timezone('utc', now()) - interval '30 days'))
  ) then
    raise exception 'social:duplicate';
  end if;

  if (
    select count(*) from public.contact_requests r
    where r.from_user = v_actor and r.created_at > timezone('utc', now()) - interval '24 hours'
  ) >= 30 then
    raise exception 'social:rate_limited';
  end if;

  begin
    insert into public.contact_requests (from_user, to_user, note)
    values (v_actor, v_to, v_note)
    returning id into v_id;
  exception when unique_violation then
    raise exception 'social:duplicate';
  end;

  request_id := v_id;
  status := 'pending';
  return next;
end;
$$;

comment on function public.send_contact_request(text, text, uuid) is
  'T8: send a contact request by @handle. Refuses self, blocks either way, no_one, existing contact, duplicates; 30 per rolling 24 h.';

create or replace function public.respond_contact_request(
  p_request_id uuid,
  p_action text,
  p_actor uuid default null
)
returns table (request_id uuid, status text, thread_id uuid)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
  v_req public.contact_requests%rowtype;
begin
  if not private.social_enabled() then
    raise exception 'social:disabled';
  end if;
  if p_action is null or p_action not in ('accept', 'ignore') then
    raise exception 'social:invalid_action';
  end if;

  select * into v_req from public.contact_requests r where r.id = p_request_id for update;
  if not found or v_req.to_user <> v_actor then
    raise exception 'social:not_found';
  end if;
  if v_req.status <> 'pending' then
    raise exception 'social:not_pending';
  end if;

  request_id := v_req.id;
  if v_req.created_at <= timezone('utc', now()) - interval '30 days' then
    update public.contact_requests r
       set status = 'expired', decided_at = timezone('utc', now())
     where r.id = v_req.id;
    status := 'expired';
    return next;
    return;
  end if;

  if p_action = 'accept' then
    thread_id := private.social_accept_request(v_req.id);
    status := 'accepted';
  else
    update public.contact_requests r
       set status = 'ignored', decided_at = timezone('utc', now())
     where r.id = v_req.id;
    status := 'ignored';
  end if;
  return next;
end;
$$;

comment on function public.respond_contact_request(uuid, text, uuid) is
  'T8: recipient accepts (creates contact + chat thread) or silently ignores a pending request.';

create or replace function public.remove_contact(p_other uuid, p_actor uuid default null)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
begin
  delete from public.contacts
   where user_a = least(v_actor, p_other) and user_b = greatest(v_actor, p_other);
  return found;
end;
$$;

comment on function public.remove_contact(uuid, uuid) is
  'T8: remove a contact (either side). The thread stays readable; messaging stops.';

create or replace function public.block_user(p_other uuid, p_actor uuid default null)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
begin
  if p_other is null or p_other = v_actor then
    raise exception 'social:self';
  end if;
  if not exists (select 1 from auth.users where id = p_other) then
    raise exception 'social:not_found';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('social_pair:' || least(v_actor, p_other)::text || greatest(v_actor, p_other)::text, 0)
  );

  insert into public.contact_blocks (blocker, blocked) values (v_actor, p_other)
  on conflict (blocker, blocked) do nothing;

  delete from public.contacts
   where user_a = least(v_actor, p_other) and user_b = greatest(v_actor, p_other);

  update public.contact_requests
     set status = 'expired', decided_at = timezone('utc', now())
   where status = 'pending'
     and ((from_user = v_actor and to_user = p_other)
          or (from_user = p_other and to_user = v_actor));
  return true;
end;
$$;

comment on function public.block_user(uuid, uuid) is
  'T8: block (works with the flag off). Two-way effect: removes the contact, expires pending requests, hides lookup / thread / messages for both.';

create or replace function public.unblock_user(p_other uuid, p_actor uuid default null)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
begin
  delete from public.contact_blocks where blocker = v_actor and blocked = p_other;
  return found;
end;
$$;

comment on function public.unblock_user(uuid, uuid) is
  'T8: lift the caller''s own block. Does not restore the contact.';

-- Both directions of the caller's requests. An ignored request reads as
-- 'pending' to its sender (until it expires), so ignoring stays silent.
create or replace function public.my_contact_requests()
returns table (
  id uuid,
  from_user uuid,
  to_user uuid,
  note text,
  status text,
  created_at timestamptz,
  outgoing boolean
)
language sql
stable
security definer
set search_path = ''
as $$
  select r.id, r.from_user, r.to_user, r.note,
         case when r.from_user = (select auth.uid()) and r.status = 'ignored'
              then 'pending' else r.status end,
         r.created_at,
         r.from_user = (select auth.uid())
    from public.contact_requests r
   where (select auth.uid()) in (r.from_user, r.to_user)
     and not private.social_blocked(r.from_user, r.to_user)
   order by r.created_at desc
   limit 200;
$$;

revoke all on function public.my_contact_requests() from public, anon;
grant execute on function public.my_contact_requests() to authenticated;

create or replace function public.send_chat_message(
  p_thread_id uuid,
  p_kind text,
  p_body text default null,
  p_card jsonb default null,
  p_actor uuid default null
)
returns table (message_id uuid, created_at timestamptz)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
  v_thread public.chat_threads%rowtype;
  v_body text := nullif(btrim(coalesce(p_body, '')), '');
  v_id uuid;
  v_at timestamptz;
begin
  if not private.social_enabled() then
    raise exception 'social:disabled';
  end if;

  -- Row lock: serialises sends in a thread so the rate count is exact.
  select * into v_thread from public.chat_threads t where t.id = p_thread_id for update;
  if not found or v_actor not in (v_thread.user_a, v_thread.user_b) then
    raise exception 'social:not_found';
  end if;
  if private.social_blocked(v_thread.user_a, v_thread.user_b)
     or not exists (
       select 1 from public.contacts c
       where c.user_a = v_thread.user_a and c.user_b = v_thread.user_b
     ) then
    raise exception 'social:not_contact';
  end if;

  if p_kind is null or p_kind not in ('text', 'share_card')
     or (p_kind = 'text' and (v_body is null or p_card is not null))
     or (p_kind = 'share_card' and p_card is null)
     or (v_body is not null and char_length(v_body) > 2000) then
    raise exception 'social:message_invalid';
  end if;

  if (
    select count(*) from public.chat_messages m
    where m.thread_id = p_thread_id and m.sender = v_actor
      and m.created_at > timezone('utc', now()) - interval '1 minute'
  ) >= 20 then
    raise exception 'social:rate_limited';
  end if;

  begin
    insert into public.chat_messages (thread_id, sender, kind, body, card)
    values (p_thread_id, v_actor, p_kind, v_body, p_card)
    returning id, chat_messages.created_at into v_id, v_at;
  exception when check_violation then
    raise exception 'social:message_invalid';
  end;

  update public.chat_threads t set last_message_at = v_at where t.id = p_thread_id;

  message_id := v_id;
  created_at := v_at;
  return next;
end;
$$;

comment on function public.send_chat_message(uuid, text, text, jsonb, uuid) is
  'T8: send a 1:1 message. Sender must be a party, the contact must exist, no block either way; 20 per sender per thread per rolling minute.';

-- ---------------------------------------------------------------------------
-- 8. Service-role-only functions (API / cron)
-- ---------------------------------------------------------------------------

create or replace function public.set_phone_discovery(
  p_user uuid,
  p_phone_hash text,
  p_enabled boolean
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_hash text := lower(btrim(coalesce(p_phone_hash, '')));
begin
  if p_user is null or v_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'social:invalid_phone_hash';
  end if;
  insert into public.phone_discovery (user_id, phone_hash, enabled, updated_at)
  values (p_user, v_hash, coalesce(p_enabled, false), timezone('utc', now()))
  on conflict (user_id) do update
    set phone_hash = excluded.phone_hash,
        enabled = excluded.enabled,
        updated_at = excluded.updated_at;
  return coalesce(p_enabled, false);
end;
$$;

comment on function public.set_phone_discovery(uuid, text, boolean) is
  'T8: API-only. Store the peppered hash of the user''s VERIFIED number and the "find me by phone" opt-in.';

create or replace function public.discover_by_phone_hashes(p_hashes text[], p_actor uuid)
returns table (user_id uuid, handle text, display_name text)
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_actor uuid := private.social_actor(p_actor);
begin
  if not private.social_enabled() then
    raise exception 'social:disabled';
  end if;
  if coalesce(cardinality(p_hashes), 0) > 200 then
    raise exception 'social:too_many_hashes';
  end if;
  return query
    select distinct d.user_id, h.handle, p.display_name
    from public.phone_discovery d
    join public.profiles p on p.id = d.user_id and p.deleted_at is null
    left join public.user_handles h on h.user_id = d.user_id
    where d.enabled
      and d.phone_hash = any (
        select lower(x) from unnest(coalesce(p_hashes, '{}'::text[])) as x
        where x ~* '^[0-9a-f]{64}$'
      )
      and d.user_id <> v_actor
      and not private.social_blocked(v_actor, d.user_id);
end;
$$;

comment on function public.discover_by_phone_hashes(text[], uuid) is
  'T8: API-only. Peppered phone hashes in (max 200), opted-in, unblocked users out.';

create or replace function public.expire_contact_requests()
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_count integer;
begin
  update public.contact_requests
     set status = 'expired', decided_at = timezone('utc', now())
   where status = 'pending'
     and created_at <= timezone('utc', now()) - interval '30 days';
  get diagnostics v_count = row_count;
  return v_count;
end;
$$;

comment on function public.expire_contact_requests() is
  'T8 cron (service role): pending requests older than 30 days -> expired. Idempotent.';

revoke all on function public.set_my_handle(text, uuid) from public, anon;
revoke all on function public.lookup_handle_card(text, uuid) from public, anon;
revoke all on function public.send_contact_request(text, text, uuid) from public, anon;
revoke all on function public.respond_contact_request(uuid, text, uuid) from public, anon;
revoke all on function public.remove_contact(uuid, uuid) from public, anon;
revoke all on function public.block_user(uuid, uuid) from public, anon;
revoke all on function public.unblock_user(uuid, uuid) from public, anon;
revoke all on function public.send_chat_message(uuid, text, text, jsonb, uuid) from public, anon;
revoke all on function public.set_phone_discovery(uuid, text, boolean) from public, anon, authenticated;
revoke all on function public.discover_by_phone_hashes(text[], uuid) from public, anon, authenticated;
revoke all on function public.expire_contact_requests() from public, anon, authenticated;

grant execute on function public.set_my_handle(text, uuid) to authenticated, service_role;
grant execute on function public.lookup_handle_card(text, uuid) to authenticated, service_role;
grant execute on function public.send_contact_request(text, text, uuid) to authenticated, service_role;
grant execute on function public.respond_contact_request(uuid, text, uuid) to authenticated, service_role;
grant execute on function public.remove_contact(uuid, uuid) to authenticated, service_role;
grant execute on function public.block_user(uuid, uuid) to authenticated, service_role;
grant execute on function public.unblock_user(uuid, uuid) to authenticated, service_role;
grant execute on function public.send_chat_message(uuid, text, text, jsonb, uuid) to authenticated, service_role;
grant execute on function public.set_phone_discovery(uuid, text, boolean) to service_role;
grant execute on function public.discover_by_phone_hashes(text[], uuid) to service_role;
grant execute on function public.expire_contact_requests() to service_role;

-- ---------------------------------------------------------------------------
-- 9. Rate scopes for the API's endpoint limits: manifest + constraint rebuilt
--    from the FULL manifest
-- ---------------------------------------------------------------------------

insert into private.rate_counter_scope_manifest (scope) values
  ('social_discover_user'),
  ('social_lookup_user'),
  ('social_message_user'),
  ('social_request_user')
on conflict (scope) do nothing;

do $$
declare
  v_list text;
begin
  select string_agg(quote_literal(scope), ', ' order by scope)
    into v_list
  from private.rate_counter_scope_manifest;
  execute 'alter table public.rate_counters drop constraint if exists rate_counters_scope_check';
  execute format(
    'alter table public.rate_counters add constraint rate_counters_scope_check check (scope in (%s))',
    v_list
  );
end;
$$;
