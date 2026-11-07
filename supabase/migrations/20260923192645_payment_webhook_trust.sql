-- D3: only the verified ingress service may create payment evidence.  Existing
-- rows retain their history but lack this versioned proof and drain as quarantined.
alter table public.webhook_events
  add column verification_version text,
  add column payload_sha256 text,
  add column verified_at timestamptz;

alter table public.webhook_events
  add constraint webhook_events_verified_proof_check check (
    signature_valid = false
    or (
      verification_version = 'lenco_hmac_sha512_v1'
      and payload_sha256 ~ '^[0-9a-f]{64}$'
      and verified_at is not null
    )
    -- D2-era signed rows cannot be promoted.  The drain may only update them
    -- into this terminal quarantine shape so a migration replay does not loop.
    or (
      verification_version is null
      and payload_sha256 is null
      and verified_at is null
      and quarantine_reason = 'untrusted_webhook_evidence'
      and processed_at is not null
    )
  ) not valid;

alter table public.webhook_events
  drop constraint if exists webhook_events_quarantine_reason_check;
alter table public.webhook_events
  add constraint webhook_events_quarantine_reason_check check (
    quarantine_reason is null
    or quarantine_reason in (
      'missing_merchant_reference',
      'unknown_merchant_reference',
      'untrusted_webhook_evidence'
    )
  );

-- 0006 granted authenticated admins table-wide access.  Remove that legacy
-- policy and every browser privilege in this forward migration; service_role
-- remains the sole database authority for evidence and quarantine replay.
drop policy if exists webhook_events_admin_all on public.webhook_events;
revoke all on table public.webhook_events from public, anon, authenticated;
grant select, insert, update, delete on table public.webhook_events to service_role;

comment on table public.webhook_events is
  'Verified inbound provider evidence. Browser roles have no table access; rows without D3 proof are quarantined by the drain.';
