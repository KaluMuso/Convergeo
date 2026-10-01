-- F3 allocation 5914277388. Reports are evidence, never money authority.
-- Additive only: legacy reconciliation_reports and its policies are untouched.
begin;

create schema if not exists reconciliation_private;
revoke all on schema reconciliation_private from public, anon, authenticated;
grant usage on schema reconciliation_private to service_role;

-- One short serialization boundary per account/currency/date, not a money lock.
create table reconciliation_private.report_streams (
  provider_account_id text not null,
  currency text not null,
  report_date date not null,
  primary key (provider_account_id, currency, report_date)
);
alter table reconciliation_private.report_streams enable row level security;
alter table reconciliation_private.report_streams force row level security;
revoke all on reconciliation_private.report_streams
  from public, anon, authenticated, service_role;

create table public.reconciliation_report_versions (
  id uuid primary key default gen_random_uuid(),
  provider_account_id text not null check (btrim(provider_account_id) <> ''),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  report_date date not null,
  cutoff_utc timestamptz not null,
  version_number bigint not null check (version_number > 0),
  parent_id uuid,
  parent_version_number bigint,
  source_version text not null check (source_version ~ '^[0-9a-f]{40}$'),
  schema_version text not null check (btrim(schema_version) <> ''),
  matcher_version text not null check (btrim(matcher_version) <> ''),
  policy_version text not null check (btrim(policy_version) <> ''),
  input_hashes jsonb not null check (jsonb_typeof(input_hashes) = 'object'),
  input_fingerprint text not null check (input_fingerprint ~ '^[0-9a-f]{64}$'),
  summary jsonb not null check (jsonb_typeof(summary) = 'object'),
  discrepancies jsonb not null check (jsonb_typeof(discrepancies) = 'object'),
  created_at timestamptz not null default now(),
  constraint reconciliation_version_partition
    unique (id, provider_account_id, currency, report_date, version_number),
  constraint reconciliation_version_number
    unique (provider_account_id, currency, report_date, version_number),
  constraint reconciliation_version_exact_inputs
    unique (provider_account_id, currency, report_date, input_fingerprint),
  constraint reconciliation_version_stream foreign key
    (provider_account_id, currency, report_date) references
    reconciliation_private.report_streams (provider_account_id, currency, report_date),
  constraint reconciliation_version_parent foreign key
    (parent_id, provider_account_id, currency, report_date, parent_version_number)
    references public.reconciliation_report_versions
    (id, provider_account_id, currency, report_date, version_number),
  constraint reconciliation_version_chain check (
    (version_number = 1 and parent_id is null and parent_version_number is null)
    or (version_number > 1 and parent_id is not null and parent_version_number is not null
        and parent_version_number = version_number - 1 and parent_id <> id)
  ),
  constraint reconciliation_version_cutoff check (
    (cutoff_utc at time zone 'UTC')::date = report_date
  ),
  constraint reconciliation_version_noncertifying check (
    summary->'certifiable' is not distinct from 'false'::jsonb
  )
);

alter table public.reconciliation_report_versions enable row level security;
alter table public.reconciliation_report_versions force row level security;
revoke all on public.reconciliation_report_versions
  from public, anon, authenticated, service_role;
grant select on public.reconciliation_report_versions to authenticated, service_role;
create policy reconciliation_version_operator_read
  on public.reconciliation_report_versions for select to authenticated
  using (public.has_role('admin'));
create policy reconciliation_version_service_read
  on public.reconciliation_report_versions for select to service_role using (true);

create function reconciliation_private.reject_report_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception 'reconciliation report versions are immutable' using errcode = '55000';
end;
$$;
revoke all on function reconciliation_private.reject_report_mutation() from public;
create trigger reconciliation_versions_immutable
  before update or delete on public.reconciliation_report_versions
  for each row execute function reconciliation_private.reject_report_mutation();

-- The only privileged writer is private. The public API below is INVOKER and
-- has no PUBLIC/anon/authenticated EXECUTE grant. No caller chooses parent/id.
create function reconciliation_private.append_report(p_report jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_account text := p_report->>'provider_account_id';
  v_currency text := p_report->>'currency';
  v_date date := (p_report->>'report_date')::date;
  v_cutoff timestamptz := (p_report->>'cutoff_utc')::timestamptz;
  v_hashes jsonb := p_report->'input_hashes';
  v_binding jsonb;
  v_summary jsonb := p_report->'summary';
  v_discrepancies jsonb := p_report->'discrepancies';
  v_fingerprint text;
  v_existing public.reconciliation_report_versions%rowtype;
  v_parent public.reconciliation_report_versions%rowtype;
  v_new public.reconciliation_report_versions%rowtype;
  v_id uuid := gen_random_uuid();
  v_number bigint;
begin
  if current_setting('role', true) is distinct from 'service_role'
     and session_user <> 'service_role' then
    raise exception 'service report writer required' using errcode = '42501';
  end if;
  if jsonb_typeof(p_report) is distinct from 'object'
     or v_account is null or btrim(v_account) = ''
     or v_currency is null or v_currency !~ '^[A-Z]{3}$'
     or v_date is null or v_cutoff is null
     or (v_cutoff at time zone 'UTC')::date <> v_date
     or coalesce(p_report->>'source_version', '') !~ '^[0-9a-f]{40}$'
     or btrim(coalesce(p_report->>'schema_version', '')) = ''
     or btrim(coalesce(p_report->>'matcher_version', '')) = ''
     or btrim(coalesce(p_report->>'policy_version', '')) = ''
     or jsonb_typeof(v_hashes) is distinct from 'object'
     or jsonb_typeof(v_summary) is distinct from 'object'
     or jsonb_typeof(v_discrepancies) is distinct from 'object'
     or v_summary->'certifiable' is distinct from 'false'::jsonb then
    raise exception 'incomplete/noncertifying reconciliation binding required'
      using errcode = '22023';
  end if;
  if coalesce(v_hashes->>'account_response_sha256', '') !~ '^[0-9a-f]{64}$'
     or coalesce(v_hashes->>'local_source_sha256', '') !~ '^[0-9a-f]{64}$'
     or jsonb_typeof(v_hashes->'transaction_response_sha256s') is distinct from 'array'
  then
    raise exception 'complete reconciliation input hashes required' using errcode = '22023';
  end if;
  if jsonb_array_length(v_hashes->'transaction_response_sha256s') = 0
     or exists (select 1 from jsonb_array_elements(v_hashes->'transaction_response_sha256s') as h(value)
                where jsonb_typeof(h.value) <> 'string'
                  or h.value#>>'{}' !~ '^[0-9a-f]{64}$') then
    raise exception 'every observed provider page requires a SHA-256' using errcode = '22023';
  end if;

  v_binding := jsonb_build_object(
    'provider_account_id', v_account, 'currency', v_currency,
    'report_date', v_date,
    'cutoff_utc', to_char(v_cutoff at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'source_version', p_report->>'source_version',
    'schema_version', p_report->>'schema_version',
    'matcher_version', p_report->>'matcher_version',
    'policy_version', p_report->>'policy_version', 'input_hashes', v_hashes
  );
  v_fingerprint := encode(sha256(convert_to(v_binding::text, 'UTF8')), 'hex');
  -- Canonical server metadata cannot be forged by the evidence caller.
  v_summary := (v_summary - array['run_id', 'input_fingerprint', 'version_number', 'parent_id'])
    || (v_binding - 'input_hashes') || jsonb_build_object('configured_account_id', v_account);

  insert into reconciliation_private.report_streams values (v_account, v_currency, v_date)
    on conflict do nothing;
  perform 1 from reconciliation_private.report_streams
    where provider_account_id = v_account and currency = v_currency and report_date = v_date
    for update;
  select * into v_existing from public.reconciliation_report_versions
    where provider_account_id = v_account and currency = v_currency
      and report_date = v_date and input_fingerprint = v_fingerprint;
  if found then
    if (v_existing.summary - array['run_id', 'input_fingerprint', 'version_number', 'parent_id'])
         is distinct from v_summary
       or v_existing.discrepancies is distinct from v_discrepancies then
      raise exception 'same inputs produced a different report; change the bound matcher/source version'
        using errcode = '22023';
    end if;
    return jsonb_build_object('created', false, 'report', to_jsonb(v_existing));
  end if;
  select * into v_parent from public.reconciliation_report_versions
    where provider_account_id = v_account and currency = v_currency and report_date = v_date
    order by version_number desc limit 1;
  v_number := coalesce(v_parent.version_number, 0) + 1;
  insert into public.reconciliation_report_versions (
    id, provider_account_id, currency, report_date, cutoff_utc, version_number,
    parent_id, parent_version_number, source_version, schema_version, matcher_version,
    policy_version, input_hashes, input_fingerprint, summary, discrepancies
  ) values (
    v_id, v_account, v_currency, v_date, v_cutoff, v_number, v_parent.id,
    v_parent.version_number, p_report->>'source_version', p_report->>'schema_version',
    p_report->>'matcher_version', p_report->>'policy_version', v_hashes, v_fingerprint,
    v_summary || jsonb_build_object('run_id', v_id, 'input_fingerprint', v_fingerprint,
                                   'version_number', v_number, 'parent_id', v_parent.id),
    v_discrepancies
  ) returning * into v_new;
  return jsonb_build_object('created', true, 'report', to_jsonb(v_new));
end;
$$;
revoke all on function reconciliation_private.append_report(jsonb)
  from public, anon, authenticated;
grant execute on function reconciliation_private.append_report(jsonb) to service_role;

create function public.append_reconciliation_report_version(p_report jsonb)
returns jsonb language sql security invoker set search_path = '' as $$
  select reconciliation_private.append_report(p_report);
$$;
revoke all on function public.append_reconciliation_report_version(jsonb)
  from public, anon, authenticated;
grant execute on function public.append_reconciliation_report_version(jsonb) to service_role;
comment on table public.reconciliation_report_versions is
  'Append-only scoped evidence versions. Legacy reports stay unversioned; no pay/release/certification authority.';
notify pgrst, 'reload schema';
commit;
