-- Web Push delivery queue (docs/plan/notification-center.md, "Web Push").
--
-- One row per (in-app notification, push subscription): the idempotency key for
-- phone alerts. Rows are written by an AFTER INSERT trigger on
-- public.in_app_notifications in the same transaction as the in-app row, but
-- only when feature flag `web_push` is ON — nothing is ever SENT inside a
-- domain transaction. The API sweeper (POST /internal/dispatch/web-push-tick,
-- called by n8n every minute) claims due rows, sends, retries with backoff and
-- deletes dead subscriptions (HTTP 404/410).
--
-- The queue holds ids only — no rendered text, keys or payloads. A writer
-- failure is downgraded to a WARNING so a push bug can never roll back an
-- order, payment or KYC transition.
--
-- Additive only. Reversible — see the DOWN block at the end of this file.

create table public.web_push_deliveries (
  id uuid primary key default gen_random_uuid(),
  notification_id uuid not null references public.in_app_notifications (id) on delete cascade,
  subscription_id uuid not null references public.web_push_subscriptions (id) on delete cascade,
  recipient_user_id uuid not null references auth.users (id) on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'sending', 'sent', 'failed', 'skipped')),
  attempts int not null default 0 check (attempts between 0 and 50),
  next_attempt_at timestamptz not null default timezone('utc', now()),
  last_status_code int check (last_status_code is null or last_status_code between 0 and 999),
  last_error text check (last_error is null or last_error ~ '^[a-z][a-z0-9_]{0,62}$'),
  sent_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint web_push_deliveries_notification_subscription_key
    unique (notification_id, subscription_id)
);

create index web_push_deliveries_due_idx
  on public.web_push_deliveries (next_attempt_at)
  where status in ('pending', 'sending');

create index web_push_deliveries_subscription_idx
  on public.web_push_deliveries (subscription_id);

create trigger web_push_deliveries_set_updated_at
  before update on public.web_push_deliveries
  for each row
  execute function public.set_updated_at();

comment on table public.web_push_deliveries is
  'Web Push send queue: one row per (in_app_notification, web_push_subscription). '
  'Service-role only; ids + delivery state, never rendered text or keys.';

alter table public.web_push_deliveries enable row level security;
alter table public.web_push_deliveries force row level security;

revoke all on public.web_push_deliveries from public, anon, authenticated;
grant all on public.web_push_deliveries to service_role;

-- ---------------------------------------------------------------------------
-- Enqueue trigger (flag-gated, same transaction as the in-app row)
-- ---------------------------------------------------------------------------

create or replace function private.web_push_enqueue_from_in_app()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
begin
  if not exists (
    select 1 from public.feature_flags where flag = 'web_push' and enabled is true
  ) then
    return null;
  end if;

  insert into public.web_push_deliveries (notification_id, subscription_id, recipient_user_id)
  select new.id, s.id, s.user_id
  from public.web_push_subscriptions s
  where s.user_id = new.recipient_user_id
    and s.audience = new.audience
  on conflict (notification_id, subscription_id) do nothing;

  return null;
exception
  when others then
    raise warning 'web_push_enqueue_from_in_app skipped (sqlstate %): %', sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.web_push_enqueue_from_in_app() from public, anon, authenticated;

create trigger in_app_notifications_web_push
  after insert on public.in_app_notifications
  for each row
  execute function private.web_push_enqueue_from_in_app();

-- Per-user send cap used by app.services.notifications.web_push.
insert into private.rate_counter_scope_manifest (scope) values
  ('web_push_send')
on conflict (scope) do nothing;

-- ---------------------------------------------------------------------------
-- DOWN (manual; run in one transaction to reverse this migration)
-- ---------------------------------------------------------------------------
-- drop trigger if exists in_app_notifications_web_push on public.in_app_notifications;
-- drop function if exists private.web_push_enqueue_from_in_app();
-- drop table if exists public.web_push_deliveries;
-- delete from private.rate_counter_scope_manifest where scope = 'web_push_send';
