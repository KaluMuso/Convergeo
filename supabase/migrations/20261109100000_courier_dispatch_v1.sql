-- Courier dispatch v1 — courier partners, per-order dispatch requests, delivery
-- chain-of-custody (handover code), audit trail, kill-switch flag.
--
-- EXTENDS the existing manual-dispatch model (D16, admin_orders.py
-- `/admin/orders/{id}/dispatch`): Lusaka delivery is still dispatched by ops, but
-- the courier is now a first-class, admin-managed record and every dispatch is a
-- guarded state machine with an append-only audit log, instead of a free-text
-- `[dispatch] courier=… | tracking: …` note on order_events.
--
-- Orders are already split per vendor (`orders.vendor_id`, one checkout_group →
-- N vendor orders), so a dispatch request is per order == per vendor sub-order.
--
--   courier_partners          admin-managed courier directory (manual | api)
--   courier_partner_zones     service areas (FK delivery_zones) + optional price
--   dispatch_requests         one row per dispatch attempt for an order
--   dispatch_request_events   append-only status audit (trigger-written)
--   dispatch_handover_codes   6-digit customer handover code + brute-force
--                             lockout state. Service-role ONLY: no client grant,
--                             so neither PostgREST nor an admin JWT can read it.
--
-- State machine (enforced here AND in app/services/dispatch/state.py):
--   requested → accepted → picked_up → delivered
--   requested|accepted → cancelled
--   requested|accepted|picked_up → failed
-- Status changes are service-role only (guard trigger); clients hold no write
-- grant on dispatch_requests at all.
--
-- Additive only: new tables, functions, triggers, one feature_flags row.
-- Reversal (manual, safe while unused):
--   drop table public.dispatch_handover_codes, public.dispatch_request_events,
--     public.dispatch_requests, public.courier_partner_zones, public.courier_partners;
--   drop function public.guard_dispatch_requests_update(),
--     public.audit_dispatch_requests_status(), public.guard_dispatch_request_events_append_only();
--   delete from public.feature_flags where flag = 'courier_dispatch';

-- ---------------------------------------------------------------------------
-- 1. courier_partners
-- ---------------------------------------------------------------------------

create table if not exists public.courier_partners (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  contact_whatsapp_e164 text,
  contact_email text,
  -- 'api' is RESERVED for the later TownStar / Yango / Platinum integrations;
  -- the API refuses to create or switch a partner to it until an adapter exists.
  integration_kind text not null default 'manual',
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint courier_partners_name_len_check
    check (char_length(btrim(name)) between 1 and 120),
  constraint courier_partners_integration_kind_check
    check (integration_kind in ('manual', 'api')),
  constraint courier_partners_whatsapp_e164_check
    check (contact_whatsapp_e164 is null or contact_whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  constraint courier_partners_email_check
    check (
      contact_email is null
      or (char_length(contact_email) <= 254 and contact_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$')
    ),
  -- A manual courier must be reachable: "Notify courier" has nowhere to go otherwise.
  constraint courier_partners_contact_present_check
    check (contact_whatsapp_e164 is not null or contact_email is not null),
  constraint courier_partners_notes_len_check
    check (notes is null or char_length(notes) <= 1000)
);

create unique index if not exists courier_partners_name_lower_key
  on public.courier_partners (lower(btrim(name)));

drop trigger if exists courier_partners_set_updated_at on public.courier_partners;
create trigger courier_partners_set_updated_at
  before update on public.courier_partners
  for each row execute function public.set_updated_at();

comment on table public.courier_partners is
  'Admin-managed courier directory for Lusaka dispatch. integration_kind=api is reserved (no adapter yet).';

-- ---------------------------------------------------------------------------
-- 2. courier_partner_zones — service areas from the existing delivery_zones
-- ---------------------------------------------------------------------------

create table if not exists public.courier_partner_zones (
  courier_partner_id uuid not null references public.courier_partners (id) on delete cascade,
  zone_key text not null references public.delivery_zones (zone_key) on update cascade on delete restrict,
  -- Optional courier price for this zone (integer ngwee). Null = quote per job.
  price_ngwee bigint check (price_ngwee is null or price_ngwee >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (courier_partner_id, zone_key)
);

create index if not exists courier_partner_zones_zone_key_idx
  on public.courier_partner_zones (zone_key);

drop trigger if exists courier_partner_zones_set_updated_at on public.courier_partner_zones;
create trigger courier_partner_zones_set_updated_at
  before update on public.courier_partner_zones
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 3. dispatch_requests
-- ---------------------------------------------------------------------------

create table if not exists public.dispatch_requests (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete restrict,
  courier_partner_id uuid not null references public.courier_partners (id) on delete restrict,
  status text not null default 'requested',
  -- Courier's own job / tracking reference, entered by ops (or an API adapter later).
  courier_reference text,
  -- Snapshots at dispatch time (integer ngwee). cod_amount_ngwee is what the
  -- rider must collect: order subtotal + delivery fee for COD orders, else 0.
  cod_amount_ngwee bigint not null default 0 check (cod_amount_ngwee >= 0),
  quoted_price_ngwee bigint check (quoted_price_ngwee is null or quoted_price_ngwee >= 0),
  -- Proof of delivery.
  pod_photo_public_id text,
  delivered_via text,
  failure_reason text,
  notify_count integer not null default 0 check (notify_count >= 0),
  last_notified_at timestamptz,
  requested_at timestamptz not null default timezone('utc', now()),
  accepted_at timestamptz,
  picked_up_at timestamptz,
  delivered_at timestamptz,
  failed_at timestamptz,
  cancelled_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint dispatch_requests_status_check
    check (status in ('requested', 'accepted', 'picked_up', 'delivered', 'failed', 'cancelled')),
  constraint dispatch_requests_courier_reference_len_check
    check (courier_reference is null or char_length(courier_reference) between 1 and 120),
  constraint dispatch_requests_failure_reason_len_check
    check (failure_reason is null or char_length(failure_reason) <= 500),
  -- Cloudinary public_id charset (folder/path + id), never a URL.
  constraint dispatch_requests_pod_public_id_check
    check (pod_photo_public_id is null or pod_photo_public_id ~ '^[A-Za-z0-9_/.-]{1,255}$'),
  constraint dispatch_requests_delivered_via_check
    check (delivered_via is null or delivered_via in ('handover_code', 'pod_photo')),
  -- Chain of custody: a delivered dispatch always says HOW it was proven.
  constraint dispatch_requests_delivered_proof_check
    check (status <> 'delivered' or delivered_via is not null),
  constraint dispatch_requests_pod_photo_proof_check
    check (delivered_via is distinct from 'pod_photo' or pod_photo_public_id is not null)
);

-- At most one in-flight dispatch per order; a failed/cancelled one may be redone.
create unique index if not exists dispatch_requests_one_active_per_order
  on public.dispatch_requests (order_id)
  where status in ('requested', 'accepted', 'picked_up');

create unique index if not exists dispatch_requests_one_delivered_per_order
  on public.dispatch_requests (order_id)
  where status = 'delivered';

create index if not exists dispatch_requests_status_requested_at_idx
  on public.dispatch_requests (status, requested_at);

create index if not exists dispatch_requests_courier_partner_id_idx
  on public.dispatch_requests (courier_partner_id);

create index if not exists dispatch_requests_order_id_created_at_idx
  on public.dispatch_requests (order_id, created_at desc);

drop trigger if exists dispatch_requests_set_updated_at on public.dispatch_requests;
create trigger dispatch_requests_set_updated_at
  before update on public.dispatch_requests
  for each row execute function public.set_updated_at();

comment on table public.dispatch_requests is
  'Per-order (== per vendor sub-order) courier dispatch. Status is a guarded state machine; '
  'transitions via app/services/dispatch only (service role), audited in dispatch_request_events.';

-- ---------------------------------------------------------------------------
-- 4. dispatch_request_events — append-only audit
-- ---------------------------------------------------------------------------

create table if not exists public.dispatch_request_events (
  id uuid primary key default gen_random_uuid(),
  dispatch_request_id uuid not null references public.dispatch_requests (id) on delete cascade,
  actor uuid,
  from_status text,
  to_status text not null,
  note text,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists dispatch_request_events_request_created_idx
  on public.dispatch_request_events (dispatch_request_id, created_at);

-- ---------------------------------------------------------------------------
-- 5. dispatch_handover_codes — secret + lockout state (service role only)
-- ---------------------------------------------------------------------------

create table if not exists public.dispatch_handover_codes (
  dispatch_request_id uuid primary key references public.dispatch_requests (id) on delete cascade,
  code text not null check (code ~ '^[0-9]{6}$'),
  failed_attempts integer not null default 0 check (failed_attempts >= 0),
  locked_until timestamptz,
  verified_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

drop trigger if exists dispatch_handover_codes_set_updated_at on public.dispatch_handover_codes;
create trigger dispatch_handover_codes_set_updated_at
  before update on public.dispatch_handover_codes
  for each row execute function public.set_updated_at();

comment on table public.dispatch_handover_codes is
  'Customer handover code per dispatch (delivery chain-of-custody v1). Readable ONLY by the '
  'service role: the API shows it to the order owner and verifies it with a lockout.';

-- ---------------------------------------------------------------------------
-- 6. Guard + audit triggers
-- ---------------------------------------------------------------------------

create or replace function public.guard_dispatch_requests_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
  allowed boolean;
begin
  if session_user not in ('postgres', 'supabase_admin') and jwt_role <> 'service_role' then
    raise exception 'dispatch_requests are server-controlled'
      using errcode = '42501';
  end if;

  if new.order_id is distinct from old.order_id then
    raise exception 'dispatch_requests.order_id is immutable';
  end if;

  if new.status is not distinct from old.status then
    return new;
  end if;

  allowed := (old.status, new.status) in (
    ('requested', 'accepted'),
    ('requested', 'cancelled'),
    ('requested', 'failed'),
    ('accepted', 'picked_up'),
    ('accepted', 'cancelled'),
    ('accepted', 'failed'),
    ('picked_up', 'delivered'),
    ('picked_up', 'failed')
  );
  if not allowed then
    raise exception 'invalid dispatch transition % -> %', old.status, new.status
      using errcode = '23514';
  end if;

  case new.status
    when 'accepted' then new.accepted_at := coalesce(new.accepted_at, timezone('utc', now()));
    when 'picked_up' then new.picked_up_at := coalesce(new.picked_up_at, timezone('utc', now()));
    when 'delivered' then new.delivered_at := coalesce(new.delivered_at, timezone('utc', now()));
    when 'failed' then new.failed_at := coalesce(new.failed_at, timezone('utc', now()));
    when 'cancelled' then new.cancelled_at := coalesce(new.cancelled_at, timezone('utc', now()));
    else null;
  end case;

  return new;
end;
$$;

drop trigger if exists dispatch_requests_guard_update on public.dispatch_requests;
create trigger dispatch_requests_guard_update
  before update on public.dispatch_requests
  for each row execute function public.guard_dispatch_requests_update();

-- Audit every insert + status change. Actor/note come from transaction-local
-- GUCs primed by app/services/dispatch (same contract as order_events).
create or replace function public.audit_dispatch_requests_status()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  actor_raw text := nullif(current_setting('app.dispatch_actor', true), '');
  note_raw text := nullif(current_setting('app.dispatch_note', true), '');
  actor_id uuid;
begin
  if actor_raw is not null and actor_raw ~ '^[0-9a-fA-F-]{36}$' then
    actor_id := actor_raw::uuid;
  end if;

  if tg_op = 'INSERT' then
    insert into public.dispatch_request_events (dispatch_request_id, actor, from_status, to_status, note)
    values (new.id, coalesce(actor_id, new.created_by), null, new.status, note_raw);
  elsif new.status is distinct from old.status then
    insert into public.dispatch_request_events (dispatch_request_id, actor, from_status, to_status, note)
    values (new.id, actor_id, old.status, new.status, note_raw);
  end if;

  return new;
end;
$$;

drop trigger if exists dispatch_requests_audit_status on public.dispatch_requests;
create trigger dispatch_requests_audit_status
  after insert or update on public.dispatch_requests
  for each row execute function public.audit_dispatch_requests_status();

-- dispatch_request_events is append-only for everyone but the migration owner.
create or replace function public.guard_dispatch_request_events_append_only()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if session_user in ('postgres', 'supabase_admin') and coalesce(auth.jwt() ->> 'role', '') = '' then
    return coalesce(new, old);
  end if;
  raise exception 'dispatch_request_events is append-only' using errcode = '42501';
end;
$$;

drop trigger if exists dispatch_request_events_append_only on public.dispatch_request_events;
create trigger dispatch_request_events_append_only
  before update or delete on public.dispatch_request_events
  for each row execute function public.guard_dispatch_request_events_append_only();

revoke all on function public.guard_dispatch_requests_update() from public, anon, authenticated;
revoke all on function public.audit_dispatch_requests_status() from public, anon, authenticated;
revoke all on function public.guard_dispatch_request_events_append_only() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 7. Row level security
-- ---------------------------------------------------------------------------

alter table public.courier_partners enable row level security;
alter table public.courier_partner_zones enable row level security;
alter table public.dispatch_requests enable row level security;
alter table public.dispatch_request_events enable row level security;
alter table public.dispatch_handover_codes enable row level security;

alter table public.courier_partners force row level security;
alter table public.courier_partner_zones force row level security;
alter table public.dispatch_requests force row level security;
alter table public.dispatch_request_events force row level security;
alter table public.dispatch_handover_codes force row level security;

-- courier_partners / courier_partner_zones: admin RLS only (read + write).
drop policy if exists courier_partners_admin_all on public.courier_partners;
create policy courier_partners_admin_all
  on public.courier_partners
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy courier_partners_admin_all on public.courier_partners is
  'Courier directory is admin-only (contacts are operational PII).';

drop policy if exists courier_partner_zones_admin_all on public.courier_partner_zones;
create policy courier_partner_zones_admin_all
  on public.courier_partner_zones
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy courier_partner_zones_admin_all on public.courier_partner_zones is
  'Courier service areas / prices are admin-only.';

-- dispatch_requests / events: admin read; writes are service-role only (no
-- client write grant). Customer + vendor views are served by the API, which
-- projects only what each party may see.
drop policy if exists dispatch_requests_admin_select on public.dispatch_requests;
create policy dispatch_requests_admin_select
  on public.dispatch_requests
  for select
  to authenticated
  using (public.has_role('admin'));

comment on policy dispatch_requests_admin_select on public.dispatch_requests is
  'Admins may read dispatches; status changes go through the guarded service-role path only.';

drop policy if exists dispatch_request_events_admin_select on public.dispatch_request_events;
create policy dispatch_request_events_admin_select
  on public.dispatch_request_events
  for select
  to authenticated
  using (public.has_role('admin'));

comment on policy dispatch_request_events_admin_select on public.dispatch_request_events is
  'Admins may read the dispatch audit trail; rows are trigger-written only.';

-- dispatch_handover_codes: NO policies and NO client grants (client-invisible).

revoke all on table public.courier_partners from anon, authenticated;
revoke all on table public.courier_partner_zones from anon, authenticated;
revoke all on table public.dispatch_requests from anon, authenticated;
revoke all on table public.dispatch_request_events from anon, authenticated;
revoke all on table public.dispatch_handover_codes from anon, authenticated;

grant select, insert, update, delete on public.courier_partners to authenticated;
grant select, insert, update, delete on public.courier_partner_zones to authenticated;
grant select on public.dispatch_requests to authenticated;
grant select on public.dispatch_request_events to authenticated;

grant all on public.courier_partners to service_role;
grant all on public.courier_partner_zones to service_role;
grant all on public.dispatch_requests to service_role;
grant select, insert on public.dispatch_request_events to service_role;
grant all on public.dispatch_handover_codes to service_role;

-- ---------------------------------------------------------------------------
-- 8. Kill-switch flag (default OFF)
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  (
    'courier_dispatch',
    false,
    'Courier dispatch v1: admin dispatch board actions, courier notify, customer handover code '
    'and vendor/customer courier status. Default OFF = kill switch (courier directory stays editable).'
  )
on conflict (flag) do nothing;
