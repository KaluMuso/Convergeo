-- 0060: Tier-1 personal organiser per-event paid GMV fraud cap (VF-P06 / BG-3 / BL-004).
--
-- Events strategy: Tier-1 organisers may sell ticketed GMV up to K20,000 (2_000_000 ngwee)
-- per event until trust is built. Cap is admin-tunable via platform_config; T2+ uncapped.
-- Enforcement lives in the API (services/events/gmv_cap.py) before paid-ticket escrow.
--
-- REVERSAL (additive + reversible):
--   delete from public.platform_config where key = 'organiser_t1_event_gmv_cap_ngwee';

insert into public.platform_config (key, value, description) values
  (
    'organiser_t1_event_gmv_cap_ngwee',
    '2000000'::jsonb,
    'Tier-1 organiser per-event paid ticket GMV cap in ngwee (K20,000). T2+ uncapped. VF-P06 / BG-3.'
  )
on conflict (key) do nothing;
