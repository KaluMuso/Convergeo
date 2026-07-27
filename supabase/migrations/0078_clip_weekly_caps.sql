-- M17-P06 — per-tier weekly clip allowance.
--
-- One row in the existing `platform_config` table (0008_config.sql), so it
-- inherits that table's FORCE RLS, public-read/admin-write policies and the
-- config_audit trigger that records every change with an actor.
--
-- Config, not code, for the same reason the listing caps are: the founder needs
-- to widen a pilot vendor's allowance — or narrow everyone's if Cloudinary
-- credits run hot — without waiting for a deploy. The API reads this on every
-- upload attempt (app/services/clips/quota.py) and falls back to these same
-- numbers if the row is missing, so a deleted row degrades to the documented
-- default rather than to "unlimited".
--
-- Tier 1 is the free tier: 3 clips per rolling seven days, per the M17 spec.
-- The window is trailing, not calendar — a calendar week would hand a vendor who
-- posted three clips on Sunday evening three more on Monday morning.
--
-- Reversible: delete the row.

insert into public.platform_config (key, value, description) values
  (
    'clip_weekly_caps',
    '{"1": 3, "2": 10, "3": 30}'::jsonb,
    'M17 clip uploads allowed per vendor per rolling 7 days, keyed by KYC tier. '
    'Counts every clip created in the window including rejected ones — a rejected '
    'clip still spent a transcode credit. Missing row falls back to the same values.'
  )
on conflict (key) do nothing;
