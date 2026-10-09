-- Staging WAHA OTP request-ID reservation. No OTP, phone, or Auth data is stored.
-- The login has no password until the owner provisions one outside migration history.
begin;

create schema otp_replay;
revoke all on schema otp_replay from public, anon, authenticated, service_role;

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

create table otp_replay.otp_delivery_replay (
  request_id text primary key check (request_id ~ '^[A-Za-z0-9_-]{8,64}$'),
  expires_at timestamptz not null
);

create index otp_delivery_replay_expires_at_idx
  on otp_replay.otp_delivery_replay (expires_at);

alter table otp_replay.otp_delivery_replay enable row level security;

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

revoke all on table otp_replay.otp_delivery_replay
  from public, anon, authenticated, service_role;

grant connect on database postgres to n8n_otp_replay;
grant usage on schema otp_replay to n8n_otp_replay;
grant insert (request_id, expires_at), select (request_id)
  on table otp_replay.otp_delivery_replay to n8n_otp_replay;

-- The workflow's INSERT is unqualified. Keep built-ins first and temporary
-- relations last so this role resolves otp_delivery_replay in otp_replay.
alter role n8n_otp_replay in database postgres
  set search_path = pg_catalog, otp_replay, pg_temp;

comment on table otp_replay.otp_delivery_replay is
  'Staging WAHA OTP replay reservation: random request IDs and expiry only; purge expired rows using a separate privileged maintenance path.';

commit;
