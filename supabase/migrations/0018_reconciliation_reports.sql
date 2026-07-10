-- M08-P07: Daily reconciliation report persistence (Lenco vs ledger diff).
-- Down (manual): drop table public.reconciliation_reports;

-- ---------------------------------------------------------------------------
-- reconciliation_reports
-- ---------------------------------------------------------------------------
create table public.reconciliation_reports (
  id uuid primary key default gen_random_uuid(),
  report_date date not null,
  summary jsonb not null default '{}'::jsonb,
  discrepancies jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint reconciliation_reports_report_date_key unique (report_date)
);

create index reconciliation_reports_report_date_idx
  on public.reconciliation_reports (report_date desc);

comment on table public.reconciliation_reports is
  'Daily Lenco-vs-ledger reconciliation; one row per calendar day (idempotent upsert).';

comment on column public.reconciliation_reports.summary is
  'Aggregate counts and balances (ngwee integers) for dashboard/digest.';

comment on column public.reconciliation_reports.discrepancies is
  'Orphaned Lenco txns, ledger-only txns, and ngwee-exact balance diffs.';

-- ---------------------------------------------------------------------------
-- Row level security — service-role writes; admin read for M13 dashboard
-- ---------------------------------------------------------------------------
alter table public.reconciliation_reports enable row level security;
alter table public.reconciliation_reports force row level security;

create policy reconciliation_reports_admin_select
  on public.reconciliation_reports
  for select
  to authenticated
  using (public.has_role('admin'));

comment on policy reconciliation_reports_admin_select on public.reconciliation_reports is
  'Platform admins may read reconciliation reports; writes are service_role only.';

grant select, insert, update, delete on table public.reconciliation_reports
  to authenticated, service_role;
