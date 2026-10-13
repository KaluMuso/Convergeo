-- WAHA OTP request-ID reservation. No OTP, phone, or Auth data is stored.
-- This shared migration creates no login or policy grant. The staging-only
-- login bootstrap is tracked separately under infra/staging/supabase/.
begin;

create schema otp_replay;
revoke all on schema otp_replay from public, anon, authenticated, service_role;

create table otp_replay.otp_delivery_replay (
  request_id text primary key check (request_id ~ '^[A-Za-z0-9_-]{8,64}$'),
  expires_at timestamptz not null
);

create index otp_delivery_replay_expires_at_idx
  on otp_replay.otp_delivery_replay (expires_at);

alter table otp_replay.otp_delivery_replay enable row level security;

revoke all on table otp_replay.otp_delivery_replay
  from public, anon, authenticated, service_role;

comment on table otp_replay.otp_delivery_replay is
  'Staging WAHA OTP replay reservation: random request IDs and expiry only; purge expired rows using a separate privileged maintenance path.';

commit;
