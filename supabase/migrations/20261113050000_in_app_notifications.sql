-- In-app notification center (docs/plan/notification-center.md).
--
-- Per-recipient in-app notifications for the customer, vendor and admin apps,
-- populated from the SAME domain events the outbox already carries:
--
--   * AFTER INSERT on public.notification_outbox — every outbox enqueue path
--     (PostgREST enqueue_outbox_row, run_sql_script, and SQL functions such as
--     apply_payment_status / COD checkout) writes its in-app rows in the same
--     transaction as the outbox row. No call site changes, nothing to drift.
--   * AFTER triggers on the guarded domain tables for the registry events that
--     are deliberately silent on WhatsApp (no template, so no outbox row):
--     KYC submitted, dispute opened, ticket issued.
--
-- Rows hold an i18n key + allow-listed params, never rendered text. Pickup
-- PINs, QR tokens, phone numbers, notes and amounts present in outbox payloads
-- are NOT copied. Admin notifications are fanned out per admin user (role
-- 'admin' in user_roles) so seen/read state is per person.
--
-- A writer failure is downgraded to a WARNING: a notification bug must never
-- roll back an order, payment or KYC transition.
--
-- Additive only. Reversible — see the DOWN block at the end of this file.

-- ---------------------------------------------------------------------------
-- 1. Tables
-- ---------------------------------------------------------------------------

create table public.in_app_notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_user_id uuid not null references auth.users (id) on delete cascade,
  audience text not null check (audience in ('customer', 'vendor', 'admin')),
  type text not null check (type ~ '^[a-z][a-z0-9_]{1,62}$'),
  i18n_key text not null check (i18n_key ~ '^notifications\.inApp\.[a-z][a-z0-9_]{1,62}$'),
  params jsonb not null default '{}'::jsonb
    check (jsonb_typeof(params) = 'object' and octet_length(params::text) <= 1024),
  link_path text check (link_path is null or link_path ~ '^/[A-Za-z0-9/_-]{0,200}$'),
  dedupe_key text not null check (char_length(dedupe_key) between 1 and 200),
  created_at timestamptz not null default timezone('utc', now()),
  seen_at timestamptz,
  read_at timestamptz,
  constraint in_app_notifications_recipient_dedupe_key
    unique (recipient_user_id, audience, dedupe_key)
);

create index in_app_notifications_feed_idx
  on public.in_app_notifications (recipient_user_id, audience, created_at desc, id desc);

create index in_app_notifications_unseen_idx
  on public.in_app_notifications (recipient_user_id, audience)
  where seen_at is null;

comment on table public.in_app_notifications is
  'Per-recipient in-app notifications (bell/badge/toasts). Written only by service-side triggers; '
  'clients read own rows and may only set seen_at/read_at on them.';

alter table public.in_app_notifications enable row level security;
alter table public.in_app_notifications force row level security;

revoke all on public.in_app_notifications from public, anon, authenticated;
grant select on public.in_app_notifications to authenticated;
grant update (seen_at, read_at) on public.in_app_notifications to authenticated;
grant all on public.in_app_notifications to service_role;

create policy in_app_notifications_select_own
  on public.in_app_notifications
  for select
  to authenticated
  using (recipient_user_id = auth.uid());

create policy in_app_notifications_update_own
  on public.in_app_notifications
  for update
  to authenticated
  using (recipient_user_id = auth.uid())
  with check (recipient_user_id = auth.uid());

-- Seen/read timestamps are monotonic: once set they never clear or move, and
-- reading implies seeing. Everything else is immutable after insert.
create or replace function private.in_app_notifications_guard_update()
returns trigger
language plpgsql
set search_path = public, private
as $$
begin
  if new.id is distinct from old.id
     or new.recipient_user_id is distinct from old.recipient_user_id
     or new.audience is distinct from old.audience
     or new.type is distinct from old.type
     or new.i18n_key is distinct from old.i18n_key
     or new.params is distinct from old.params
     or new.link_path is distinct from old.link_path
     or new.dedupe_key is distinct from old.dedupe_key
     or new.created_at is distinct from old.created_at then
    raise exception 'in_app_notifications rows are immutable except seen_at/read_at'
      using errcode = '42501';
  end if;
  new.seen_at := coalesce(old.seen_at, new.seen_at);
  new.read_at := coalesce(old.read_at, new.read_at);
  if new.read_at is not null and new.seen_at is null then
    new.seen_at := new.read_at;
  end if;
  return new;
end;
$$;

revoke all on function private.in_app_notifications_guard_update() from public, anon, authenticated;

create trigger in_app_notifications_guard_update
  before update on public.in_app_notifications
  for each row
  execute function private.in_app_notifications_guard_update();

create table public.web_push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  audience text not null check (audience in ('customer', 'vendor')),
  endpoint text not null unique
    check (endpoint ~ '^https://' and char_length(endpoint) <= 1024),
  p256dh text not null check (char_length(p256dh) between 16 and 256),
  auth_secret text not null check (char_length(auth_secret) between 8 and 64),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index web_push_subscriptions_user_idx
  on public.web_push_subscriptions (user_id, audience);

create trigger web_push_subscriptions_set_updated_at
  before update on public.web_push_subscriptions
  for each row
  execute function public.set_updated_at();

comment on table public.web_push_subscriptions is
  'Web Push subscriptions (flag web_push, default OFF). Written by the API for the caller only; '
  'clients may read/delete their own rows.';

alter table public.web_push_subscriptions enable row level security;
alter table public.web_push_subscriptions force row level security;

revoke all on public.web_push_subscriptions from public, anon, authenticated;
grant select, delete on public.web_push_subscriptions to authenticated;
grant all on public.web_push_subscriptions to service_role;

create policy web_push_subscriptions_select_own
  on public.web_push_subscriptions
  for select
  to authenticated
  using (user_id = auth.uid());

create policy web_push_subscriptions_delete_own
  on public.web_push_subscriptions
  for delete
  to authenticated
  using (user_id = auth.uid());

insert into public.feature_flags (flag, enabled, description) values
  (
    'web_push',
    false,
    'Web Push for the customer + vendor PWAs (notification center). Default OFF until the founder '
    'sets VAPID env vars — see docs/plan/notification-center.md.'
  )
on conflict (flag) do nothing;

-- Rate-limit scopes used by services/api/app/routers/notifications.py.
insert into private.rate_counter_scope_manifest (scope) values
  ('notifications_read'),
  ('notifications_write'),
  ('web_push_subscribe')
on conflict (scope) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Writers (service-side only)
-- ---------------------------------------------------------------------------

create or replace function private.enqueue_in_app_notification(
  p_recipient uuid,
  p_audience text,
  p_type text,
  p_params jsonb,
  p_link_path text,
  p_dedupe_key text
)
returns void
language plpgsql
security definer
set search_path = public, private
as $$
begin
  if p_recipient is null then
    return;
  end if;
  insert into public.in_app_notifications (
    recipient_user_id, audience, type, i18n_key, params, link_path, dedupe_key
  ) values (
    p_recipient, p_audience, p_type, 'notifications.inApp.' || p_type,
    coalesce(p_params, '{}'::jsonb), p_link_path, p_dedupe_key
  )
  on conflict (recipient_user_id, audience, dedupe_key) do nothing;
end;
$$;

create or replace function private.enqueue_admin_in_app_notification(
  p_type text,
  p_params jsonb,
  p_link_path text,
  p_dedupe_key text
)
returns void
language plpgsql
security definer
set search_path = public, private
as $$
begin
  insert into public.in_app_notifications (
    recipient_user_id, audience, type, i18n_key, params, link_path, dedupe_key
  )
  select ur.user_id, 'admin', p_type, 'notifications.inApp.' || p_type,
         coalesce(p_params, '{}'::jsonb), p_link_path, p_dedupe_key
  from public.user_roles ur
  join auth.users u on u.id = ur.user_id
  where ur.role = 'admin'
  on conflict (recipient_user_id, audience, dedupe_key) do nothing;
end;
$$;

-- Short, non-sensitive human reference for an id (first 8 hex chars, upper).
create or replace function private.in_app_short_ref(p_id uuid)
returns text
language sql
immutable
set search_path = public
as $$ select upper(left(p_id::text, 8)) $$;

revoke all on function private.enqueue_in_app_notification(uuid, text, text, jsonb, text, text)
  from public, anon, authenticated;
revoke all on function private.enqueue_admin_in_app_notification(text, jsonb, text, text)
  from public, anon, authenticated;
revoke all on function private.in_app_short_ref(uuid) from public, anon, authenticated;
grant execute on function private.enqueue_in_app_notification(uuid, text, text, jsonb, text, text)
  to service_role;
grant execute on function private.enqueue_admin_in_app_notification(text, jsonb, text, text)
  to service_role;

-- Safe uuid cast (outbox payloads are jsonb written by many paths).
create or replace function private.in_app_try_uuid(p_value text)
returns uuid
language plpgsql
immutable
set search_path = public
as $$
begin
  if p_value is null
     or p_value !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then
    return null;
  end if;
  return p_value::uuid;
end;
$$;

revoke all on function private.in_app_try_uuid(text) from public, anon, authenticated;

-- Order-scoped helper: customer and/or vendor-owner row for one order event.
create or replace function private.in_app_for_order(
  p_order_id uuid,
  p_type text,
  p_notify_customer boolean,
  p_notify_vendor boolean
)
returns void
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_customer uuid;
  v_vendor_owner uuid;
  v_params jsonb;
begin
  if p_order_id is null then
    return;
  end if;
  select o.customer_id, v.owner_user_id
    into v_customer, v_vendor_owner
  from public.orders o
  left join public.vendors v on v.id = o.vendor_id
  where o.id = p_order_id;
  if not found then
    return;
  end if;
  v_params := jsonb_build_object('ref', private.in_app_short_ref(p_order_id));
  if p_notify_customer then
    perform private.enqueue_in_app_notification(
      v_customer, 'customer', p_type, v_params,
      '/account/orders/' || p_order_id::text, p_type || ':' || p_order_id::text
    );
  end if;
  if p_notify_vendor then
    perform private.enqueue_in_app_notification(
      v_vendor_owner, 'vendor', p_type, v_params,
      '/orders/' || p_order_id::text, p_type || ':' || p_order_id::text
    );
  end if;
end;
$$;

revoke all on function private.in_app_for_order(uuid, text, boolean, boolean)
  from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Outbox → in-app (same transaction as the outbox row)
-- ---------------------------------------------------------------------------

create or replace function private.in_app_from_outbox()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_payload jsonb := coalesce(new.payload, '{}'::jsonb);
  v_order uuid := private.in_app_try_uuid(v_payload ->> 'order_id');
  v_recipient uuid := private.in_app_try_uuid(v_payload ->> 'recipient_id');
  v_vendor uuid := private.in_app_try_uuid(v_payload ->> 'vendor_id');
  v_thread uuid := private.in_app_try_uuid(v_payload ->> 'thread_id');
  v_job uuid := private.in_app_try_uuid(v_payload ->> 'job_id');
  v_owner uuid;
  v_status_type text;
begin
  case new.template
    when 'vendor_new_order' then
      perform private.in_app_for_order(v_order, 'order_placed', true, true);

    when 'order_status_changed' then
      -- Vendor-driven transitions (vendor_orders router). There is no Meta
      -- template for this outbox row, so before this migration the customer
      -- received nothing at all when a vendor confirmed/packed/shipped.
      v_status_type := case v_payload ->> 'to_status'
        when 'confirmed' then 'order_confirmed'
        when 'cancelled' then 'order_rejected'
        when 'processing' then 'order_packed'
        when 'shipped' then 'order_shipped'
        when 'ready' then 'order_ready_pickup'
        when 'delivered' then 'order_delivered'
        else null
      end;
      if v_status_type is not null then
        perform private.in_app_for_order(
          v_order, v_status_type, true, v_status_type = 'order_delivered'
        );
      end if;

    when 'order_confirmed', 'order_shipped', 'order_ready_pickup' then
      perform private.in_app_for_order(v_order, new.template, true, false);

    when 'order_delivered' then
      perform private.in_app_for_order(v_order, 'order_delivered', true, true);

    when 'kyc_approved', 'kyc_rejected' then
      select owner_user_id into v_owner from public.vendors where id = v_vendor;
      perform private.enqueue_in_app_notification(
        v_owner, 'vendor', new.template, '{}'::jsonb, '/onboarding/status',
        split_part(new.dedupe_key, ':', 1) || ':' || split_part(new.dedupe_key, ':', 2)
      );

    when 'rfq_opened' then
      if v_thread is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'vendor', 'rfq_received', '{}'::jsonb, '/rfq',
          'rfq_received:' || v_thread::text
        );
      end if;

    when 'rfq_quoted' then
      if v_thread is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'customer', 'quote_received', '{}'::jsonb,
          '/account/quotes/' || v_thread::text, 'quote_received:' || new.dedupe_key
        );
      end if;

    when 'rfq_job_broadcast' then
      if v_job is not null then
        perform private.enqueue_in_app_notification(
          v_recipient, 'vendor', 'job_matched', '{}'::jsonb, '/jobs',
          'job_matched:' || v_job::text
        );
      end if;

    else
      null;
  end case;
  return null;
exception
  when others then
    raise warning 'in_app_from_outbox skipped (template %, sqlstate %): %',
      new.template, sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.in_app_from_outbox() from public, anon, authenticated;

create trigger notification_outbox_in_app
  after insert on public.notification_outbox
  for each row
  execute function private.in_app_from_outbox();

-- ---------------------------------------------------------------------------
-- 4. Registry-silent events (no outbox row) — domain-table triggers
-- ---------------------------------------------------------------------------

create or replace function private.in_app_from_kyc_record()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_owner uuid;
  v_dedupe text;
begin
  if new.status <> 'submitted'
     or (tg_op = 'UPDATE' and old.status is not distinct from new.status) then
    return null;
  end if;
  v_dedupe := 'kyc_submitted:' || new.id::text || ':'
              || to_char(new.updated_at, 'YYYYMMDDHH24MISSUS');
  select owner_user_id into v_owner from public.vendors where id = new.vendor_id;
  perform private.enqueue_in_app_notification(
    v_owner, 'vendor', 'kyc_submitted', '{}'::jsonb, '/onboarding/status', v_dedupe
  );
  perform private.enqueue_admin_in_app_notification(
    'kyc_submitted', '{}'::jsonb, '/kyc/' || new.id::text, v_dedupe
  );
  return null;
exception
  when others then
    raise warning 'in_app_from_kyc_record skipped (sqlstate %): %', sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.in_app_from_kyc_record() from public, anon, authenticated;

create trigger kyc_records_in_app
  after insert or update of status on public.kyc_records
  for each row
  execute function private.in_app_from_kyc_record();

create or replace function private.in_app_from_dispute()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_owner uuid;
  v_params jsonb := jsonb_build_object('ref', private.in_app_short_ref(new.order_id));
begin
  select v.owner_user_id into v_owner
  from public.orders o
  join public.vendors v on v.id = o.vendor_id
  where o.id = new.order_id;
  perform private.enqueue_in_app_notification(
    v_owner, 'vendor', 'dispute_opened', v_params,
    '/disputes/' || new.id::text, 'dispute_opened:' || new.id::text
  );
  perform private.enqueue_admin_in_app_notification(
    'dispute_opened', v_params, '/disputes/' || new.id::text,
    'dispute_opened:' || new.id::text
  );
  return null;
exception
  when others then
    raise warning 'in_app_from_dispute skipped (sqlstate %): %', sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.in_app_from_dispute() from public, anon, authenticated;

create trigger disputes_in_app
  after insert on public.disputes
  for each row
  execute function private.in_app_from_dispute();

create or replace function private.in_app_from_ticket()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
begin
  if new.status <> 'issued' then
    return null;
  end if;
  -- One notification per purchase line (a 5-ticket order is one alert).
  perform private.enqueue_in_app_notification(
    new.holder_user_id, 'customer', 'ticket_issued', '{}'::jsonb, '/account/tickets',
    'ticket_issued:' || coalesce(new.order_item_id, new.id)::text
  );
  return null;
exception
  when others then
    raise warning 'in_app_from_ticket skipped (sqlstate %): %', sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.in_app_from_ticket() from public, anon, authenticated;

create trigger tickets_in_app
  after insert on public.tickets
  for each row
  execute function private.in_app_from_ticket();

-- ---------------------------------------------------------------------------
-- DOWN (manual; run in one transaction to reverse this migration)
-- ---------------------------------------------------------------------------
-- drop trigger if exists tickets_in_app on public.tickets;
-- drop trigger if exists disputes_in_app on public.disputes;
-- drop trigger if exists kyc_records_in_app on public.kyc_records;
-- drop trigger if exists notification_outbox_in_app on public.notification_outbox;
-- drop function if exists private.in_app_from_ticket();
-- drop function if exists private.in_app_from_dispute();
-- drop function if exists private.in_app_from_kyc_record();
-- drop function if exists private.in_app_from_outbox();
-- drop function if exists private.in_app_for_order(uuid, text, boolean, boolean);
-- drop function if exists private.in_app_try_uuid(text);
-- drop function if exists private.in_app_short_ref(uuid);
-- drop function if exists private.enqueue_admin_in_app_notification(text, jsonb, text, text);
-- drop function if exists private.enqueue_in_app_notification(uuid, text, text, jsonb, text, text);
-- drop table if exists public.web_push_subscriptions;
-- drop table if exists public.in_app_notifications;
-- drop function if exists private.in_app_notifications_guard_update();
-- delete from public.feature_flags where flag = 'web_push';
-- delete from private.rate_counter_scope_manifest
--   where scope in ('notifications_read', 'notifications_write', 'web_push_subscribe');
