-- M17 — Vergeo Clips: the two config gates that hold the mountain closed.
--
-- No tables, no policies: both rows live in the existing `feature_flags` table
-- (0008_config.sql) and therefore inherit its FORCE RLS, public-read/admin-write
-- policies, and the config_audit trigger that records every flip.
--
-- `clips` (F-V1) — the master gate. OFF by default, and that default is what
-- makes merging M17 safe before F-V4 is answered: while it is off there is no
-- customer entry point and no upload path, so **no clip can spend a Cloudinary
-- transcode credit**. Flip it only after confirming plan headroom.
--
-- `clips_comments` (F-V2) — the comment surface. Built, moderated, rate-limited
-- and screened, but shipped OFF, following the spec's own recommendation of
-- likes-only for beta week 1. Turning comments on is a config change, not a
-- deploy; turning them back off is the kill switch if moderation load bites.
--
-- Both are read fresh on every request (app/services/clips/flags.py), so a flip
-- takes effect immediately with no restart.
--
-- Reversible: delete the two rows.

insert into public.feature_flags (flag, enabled, description) values
  (
    'clips',
    false,
    'M17 Vergeo Clips master gate (F-V1) — when OFF there is no customer feed and no '
    'upload path, so no Cloudinary transcode credit can be spent. Default OFF.'
  ),
  (
    'clips_comments',
    false,
    'M17 clip comments (F-V2) — built, moderated, rate-limited and keyword-screened, '
    'but OFF for beta week 1 (likes-only). Flip via admin config; no deploy needed.'
  )
on conflict (flag) do nothing;
