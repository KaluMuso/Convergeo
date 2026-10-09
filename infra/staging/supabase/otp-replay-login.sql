-- Operational staging-only bootstrap, NOT part of supabase/migrations.
-- Apply only through scripts/ops/apply-otp-replay-login-staging.py, which binds
-- the Management API request to project iyasmrmbcrvlfxpzescb.
begin;

-- RUNNER_INJECTS_STAGING_PROJECT_GUARD
do $$
begin
  if current_setting('otp_replay.target_project_ref', true)
     is distinct from 'iyasmrmbcrvlfxpzescb' then
    raise exception 'OTP replay login requires the approved staging project';
  end if;
  if current_database() <> 'postgres' then
    raise exception 'OTP replay login requires database postgres';
  end if;
  if to_regclass('otp_replay.otp_delivery_replay') is null then
    raise exception 'OTP replay table migration must be applied first';
  end if;
  if exists (select 1 from pg_roles where rolname = 'n8n_otp_replay') then
    raise exception 'OTP replay login already exists; inspect before changing it';
  end if;
end $$;

create role n8n_otp_replay with
  login
  noinherit
  nosuperuser
  nocreatedb
  nocreaterole
  noreplication
  nobypassrls
  connection limit 2
  password null;

create policy n8n_otp_replay_insert
  on otp_replay.otp_delivery_replay
  for insert to n8n_otp_replay
  with check (
    expires_at > now()
    and expires_at <= now() + interval '1 day 1 minute'
  );

create policy n8n_otp_replay_select
  on otp_replay.otp_delivery_replay
  for select to n8n_otp_replay
  using (true);

grant connect on database postgres to n8n_otp_replay;
grant usage on schema otp_replay to n8n_otp_replay;
grant insert (request_id, expires_at), select (request_id)
  on table otp_replay.otp_delivery_replay to n8n_otp_replay;

-- The n8n query is unqualified. Built-ins resolve first, then this schema.
alter role n8n_otp_replay in database postgres
  set search_path = pg_catalog, otp_replay, pg_temp;

commit;
