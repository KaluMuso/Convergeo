-- M18-P00 — WAHA verified-vendor product-intake: kill-switch flag + pilot allowlist.
--
-- D35 (amends D15) re-opens WAHA SOLELY as an isolated, inbound-only, 1:1
-- verified-vendor product-intake lane. This migration ships the two config rows
-- every later M18 pebble reads. It creates NO tables and NO policies: both rows
-- live in the existing config tables (0008_config.sql) and therefore inherit
-- their FORCE RLS, public-read/admin-write policies, and the config_audit
-- trigger that records every flip (actor, before/after).
--
-- The flag defaults to FALSE. That default IS the kill switch: the ingestion
-- handler's first check is this flag, so "off" means every inbound event is
-- ignored with no draft created and no reply sent (there is no reply path —
-- the lane is strictly inbound-only).
--
-- The allowlist defaults to an EMPTY array so that flipping the flag on can
-- never mean "open to all vendors" before the founder's Stage-1 pilot sign-off
-- (docs/ops/waha-vendor-intake.md §10).
--
-- Reversible: delete the two rows.

insert into public.feature_flags (flag, enabled, description) values
  (
    'waha_vendor_intake',
    false,
    'WAHA verified-vendor product intake (D35, Lane 2) — inbound-only, 1:1, draft-producing. '
    'Default OFF = the kill switch. Requires founder Stage-1 pilot approval before enabling.'
  )
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  (
    'waha_intake_vendor_allowlist',
    '[]'::jsonb,
    'Pilot scoping for WAHA vendor intake (D35 §9): JSON array of vendor_id strings permitted '
    'to use the intake lane. Empty = nobody, so enabling the flag alone never opens the lane '
    'to all vendors. Widening this list is itself an audited config change.'
  )
on conflict (key) do nothing;
