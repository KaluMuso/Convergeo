-- M10-P07: Ticket transfer-to-friend (free transfer only, no resale — D2 scope).
-- Sender initiates a transfer by phone number until T-6h before the event instance
-- starts; recipient claims on signup/login by verified phone match. Reassignment of
-- tickets.holder_user_id + reissue of qr_secret/pin_hash happens server-side only
-- (see services/api/app/routers/ticket_transfer.py) — this table only records the
-- transfer offer lifecycle, it never itself grants ticket access.
--
-- Rollback: `drop table if exists public.ticket_transfers cascade;` — purely additive,
-- no existing table/column/policy is modified.

create table public.ticket_transfers (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.tickets (id) on delete cascade,
  from_user_id uuid not null references auth.users (id) on delete cascade,
  to_phone text not null,
  status text not null default 'pending'
    check (status in ('pending', 'claimed', 'cancelled', 'expired')),
  expires_at timestamptz not null,
  claimed_by_user_id uuid references auth.users (id) on delete set null,
  claimed_at timestamptz,
  cancelled_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

-- One pending transfer per ticket at a time (D2: initiate cancels/claims before a
-- second one may be created for the same ticket).
create unique index ticket_transfers_ticket_id_pending_uidx
  on public.ticket_transfers (ticket_id)
  where status = 'pending';

create index ticket_transfers_from_user_id_idx on public.ticket_transfers (from_user_id);
create index ticket_transfers_to_phone_pending_idx
  on public.ticket_transfers (to_phone)
  where status = 'pending';

create trigger ticket_transfers_set_updated_at
  before update on public.ticket_transfers
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.ticket_transfers enable row level security;
alter table public.ticket_transfers force row level security;

create policy ticket_transfers_sender_select
  on public.ticket_transfers
  for select
  to authenticated
  using (from_user_id = (select auth.uid()));

comment on policy ticket_transfers_sender_select on public.ticket_transfers is
  'Senders may read the transfers they initiated.';

create policy ticket_transfers_admin_select
  on public.ticket_transfers
  for select
  to authenticated
  using (public.has_role('admin'));

comment on policy ticket_transfers_admin_select on public.ticket_transfers is
  'Platform admins may read every ticket transfer.';

-- No insert/update/delete policies are defined for `authenticated`: initiate,
-- cancel, and claim are server-controlled state transitions executed with the
-- service-role client from ticket_transfer.py (mirrors tickets' server-only write
-- posture) — never raw client UPDATEs against this table.
grant select, insert, update, delete on table public.ticket_transfers to authenticated, service_role;
