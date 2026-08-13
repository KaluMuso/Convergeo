-- Events strategy completion foundation.
--
-- This migration is deliberately additive. Browser clients never receive direct
-- access to the operational tables below: the FastAPI service owns access-code
-- verification, team invitations, recurring-instance materialisation, event
-- refund jobs, settlement holds, and marketing attribution.

-- Do not retain a short-code digest on the broadly selected events row. The
-- previous public RLS policy prevents anonymous exposure, but separating the
-- credential makes accidental future projection of events harmless.
create table public.event_access_credentials (
  event_id uuid primary key references public.events (id) on delete cascade,
  code_hash text not null,
  version bigint not null default 1 check (version > 0),
  created_at timestamptz not null default timezone('utc', now()),
  rotated_at timestamptz not null default timezone('utc', now())
);

insert into public.event_access_credentials (event_id, code_hash)
select id, access_code_hash
from public.events
where visibility = 'private'
  and access_code_hash is not null
on conflict (event_id) do nothing;

update public.events
set access_code_hash = null
where access_code_hash is not null;

alter table public.events
  drop constraint if exists events_access_code_hash_private_check;

alter table public.events
  add constraint events_access_code_hash_retired_check
  check (access_code_hash is null) not valid;

alter table public.events
  validate constraint events_access_code_hash_retired_check;

alter table public.events
  add column if not exists recurrence_rule text,
  add column if not exists recurrence_timezone text,
  add column if not exists recurrence_until timestamptz,
  add column if not exists recurrence_horizon_days int not null default 90
    check (recurrence_horizon_days between 14 and 366),
  add column if not exists platform_fee_payer text not null default 'organiser'
    check (platform_fee_payer in ('organiser', 'buyer')),
  add column if not exists cancellation_reason text,
  add column if not exists cancelled_at timestamptz,
  add column if not exists cancelled_by uuid references auth.users (id) on delete set null;

-- Retain ``standard`` as a compatibility value while new organiser clients use
-- the strategy terms single/multi_day/recurring/free_rsvp/private.
alter table public.events
  drop constraint if exists events_event_type_check;
alter table public.events
  add constraint events_event_type_check
  check (event_type in ('standard', 'single', 'multi_day', 'recurring', 'free_rsvp', 'private'));

-- The pre-strategy ``recurring`` discriminator was a settlement hint, not a
-- real schedule. Preserve its existing behaviour as standard rather than
-- inventing a rule that could create dates unexpectedly.
update public.events
set event_type = 'standard'
where event_type = 'recurring'
  and recurrence_rule is null;

alter table public.events
  add constraint events_recurrence_shape_check
  check (
    (event_type = 'recurring' and recurrence_rule is not null and recurrence_timezone is not null)
    or (event_type <> 'recurring' and recurrence_rule is null and recurrence_timezone is null)
  ) not valid;

comment on column public.events.recurrence_rule is
  'RFC5545 RRULE owned by the service; only future event_instances are materialised.';
comment on column public.events.platform_fee_payer is
  'Paid-event fee disclosure policy: organiser (default) or buyer pass-through.';

alter table public.event_instances
  add column if not exists recurrence_key text,
  add column if not exists status text not null default 'scheduled'
    check (status in ('scheduled', 'cancelled', 'completed'));

create unique index if not exists event_instances_event_recurrence_key_key
  on public.event_instances (event_id, recurrence_key)
  where recurrence_key is not null;
create index if not exists event_instances_event_status_starts_idx
  on public.event_instances (event_id, status, starts_at);

create table public.event_team_members (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null check (role in ('owner', 'manager', 'door')),
  invited_by uuid references auth.users (id) on delete set null,
  accepted_at timestamptz not null default timezone('utc', now()),
  revoked_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint event_team_members_event_user_key unique (event_id, user_id)
);
create unique index event_team_members_one_owner_key
  on public.event_team_members (event_id)
  where role = 'owner' and revoked_at is null;
create index event_team_members_user_active_idx
  on public.event_team_members (user_id, event_id)
  where revoked_at is null;
create trigger event_team_members_set_updated_at
  before update on public.event_team_members
  for each row execute function public.set_updated_at();

create table public.event_team_invites (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  role text not null check (role in ('manager', 'door')),
  invitee_phone text not null check (btrim(invitee_phone) <> ''),
  token_digest text not null unique,
  invited_by uuid not null references auth.users (id) on delete restrict,
  status text not null default 'pending'
    check (status in ('pending', 'accepted', 'revoked', 'expired')),
  expires_at timestamptz not null,
  accepted_by uuid references auth.users (id) on delete set null,
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint event_team_invites_expiry_after_create_check check (expires_at > created_at)
);
create index event_team_invites_event_status_idx on public.event_team_invites (event_id, status);
create unique index event_team_invites_event_phone_pending_key
  on public.event_team_invites (event_id, invitee_phone)
  where status = 'pending';
create trigger event_team_invites_set_updated_at
  before update on public.event_team_invites
  for each row execute function public.set_updated_at();

create table public.event_reschedules (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  actor_user_id uuid not null references auth.users (id) on delete restrict,
  reason text not null check (btrim(reason) <> ''),
  old_schedule jsonb not null,
  new_schedule jsonb not null,
  old_venue text,
  new_venue text,
  announced_at timestamptz not null default timezone('utc', now()),
  opt_out_deadline timestamptz not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint event_reschedules_deadline_check check (opt_out_deadline > announced_at)
);
create index event_reschedules_event_announced_idx on public.event_reschedules (event_id, announced_at desc);

create table public.event_gmv_reservations (
  checkout_group_id uuid primary key references public.checkout_groups (id) on delete cascade,
  event_id uuid not null references public.events (id) on delete restrict,
  organiser_vendor_id uuid not null references public.vendors (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  status text not null default 'reserved'
    check (status in ('reserved', 'captured', 'released', 'cancelled')),
  expires_at timestamptz not null,
  captured_at timestamptz,
  released_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index event_gmv_reservations_event_status_idx
  on public.event_gmv_reservations (event_id, status, expires_at);
create trigger event_gmv_reservations_set_updated_at
  before update on public.event_gmv_reservations
  for each row execute function public.set_updated_at();

create table public.event_settlement_snapshots (
  order_id uuid primary key references public.orders (id) on delete cascade,
  event_id uuid not null references public.events (id) on delete restrict,
  instance_id uuid not null references public.event_instances (id) on delete restrict,
  schedule jsonb not null,
  status text not null default 'active'
    check (status in ('active', 'held_for_reschedule', 'released', 'cancelled')),
  held_by_reschedule_id uuid references public.event_reschedules (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index event_settlement_snapshots_event_status_idx
  on public.event_settlement_snapshots (event_id, status);
create trigger event_settlement_snapshots_set_updated_at
  before update on public.event_settlement_snapshots
  for each row execute function public.set_updated_at();

alter table public.payouts
  add column if not exists payout_kind text not null default 'vendor'
    check (payout_kind in ('vendor', 'customer_refund'));
create unique index if not exists payouts_lenco_reference_key
  on public.payouts (lenco_reference);
drop policy if exists payouts_vendor_select on public.payouts;
create policy payouts_vendor_select
  on public.payouts for select to authenticated
  using (
    payout_kind = 'vendor'
    and exists (
      select 1 from public.vendors v
      where v.id = payouts.vendor_id and v.owner_user_id = (select auth.uid())
    )
  );

alter table public.refunds
  drop constraint if exists refunds_status_check;
alter table public.refunds
  add constraint refunds_status_check
  check (status in ('pending', 'processing', 'awaiting_payout', 'needs_destination', 'manual_review', 'completed', 'failed'));

create table public.event_refund_jobs (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  order_id uuid not null references public.orders (id) on delete restrict,
  customer_id uuid not null references auth.users (id) on delete restrict,
  source text not null check (source in ('organiser_cancel', 'buyer_cancel', 'reschedule_opt_out')),
  source_key text not null,
  policy_snapshot jsonb not null,
  amount_ngwee bigint not null check (amount_ngwee >= 0),
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'awaiting_payout', 'needs_destination', 'manual_review', 'completed', 'dead')),
  refund_id uuid references public.refunds (id) on delete set null,
  payout_id uuid references public.payouts (id) on delete set null,
  attempts int not null default 0 check (attempts >= 0),
  next_retry_at timestamptz,
  locked_at timestamptz,
  last_error text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint event_refund_jobs_source_key unique (event_id, order_id, source, source_key)
);
create index event_refund_jobs_work_idx
  on public.event_refund_jobs (status, next_retry_at, created_at);
create trigger event_refund_jobs_set_updated_at
  before update on public.event_refund_jobs
  for each row execute function public.set_updated_at();

create table public.event_promo_codes (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  code text not null,
  discount_kind text not null check (discount_kind in ('percent', 'fixed')),
  discount_value int not null check (discount_value > 0),
  max_redemptions int check (max_redemptions > 0),
  starts_at timestamptz,
  ends_at timestamptz,
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint event_promo_codes_event_code_key unique (event_id, code),
  constraint event_promo_codes_window_check check (ends_at is null or starts_at is null or ends_at > starts_at)
);
create trigger event_promo_codes_set_updated_at
  before update on public.event_promo_codes
  for each row execute function public.set_updated_at();

create table public.event_affiliates (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  user_id uuid references auth.users (id) on delete set null,
  code text not null,
  commission_bps int not null default 0 check (commission_bps between 0 and 10000),
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint event_affiliates_event_code_key unique (event_id, code)
);
create trigger event_affiliates_set_updated_at
  before update on public.event_affiliates
  for each row execute function public.set_updated_at();

create table public.event_campaigns (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  name text not null check (btrim(name) <> ''),
  channel text not null check (channel in ('email', 'sms', 'whatsapp', 'share')),
  audience text not null check (audience in ('past_attendees', 'ticket_holders', 'manual')),
  status text not null default 'draft' check (status in ('draft', 'scheduled', 'sent', 'cancelled')),
  scheduled_at timestamptz,
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create trigger event_campaigns_set_updated_at
  before update on public.event_campaigns
  for each row execute function public.set_updated_at();

-- Only the backend can see or mutate operational event data. Explicit grants
-- are required because the Data API may not auto-expose newly created tables.
alter table public.event_access_credentials enable row level security;
alter table public.event_access_credentials force row level security;
alter table public.event_team_members enable row level security;
alter table public.event_team_members force row level security;
alter table public.event_team_invites enable row level security;
alter table public.event_team_invites force row level security;
alter table public.event_reschedules enable row level security;
alter table public.event_reschedules force row level security;
alter table public.event_gmv_reservations enable row level security;
alter table public.event_gmv_reservations force row level security;
alter table public.event_settlement_snapshots enable row level security;
alter table public.event_settlement_snapshots force row level security;
alter table public.event_refund_jobs enable row level security;
alter table public.event_refund_jobs force row level security;
alter table public.event_promo_codes enable row level security;
alter table public.event_promo_codes force row level security;
alter table public.event_affiliates enable row level security;
alter table public.event_affiliates force row level security;
alter table public.event_campaigns enable row level security;
alter table public.event_campaigns force row level security;

revoke all on table public.event_access_credentials, public.event_team_members,
  public.event_team_invites, public.event_reschedules, public.event_gmv_reservations,
  public.event_settlement_snapshots, public.event_refund_jobs, public.event_promo_codes,
  public.event_affiliates, public.event_campaigns from anon, authenticated;
grant all on table public.event_access_credentials, public.event_team_members,
  public.event_team_invites, public.event_reschedules, public.event_gmv_reservations,
  public.event_settlement_snapshots, public.event_refund_jobs, public.event_promo_codes,
  public.event_affiliates, public.event_campaigns to service_role;
