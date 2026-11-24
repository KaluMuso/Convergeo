-- Clips pilot — per-vendor allowlist, viewer gate, and a re-arming spend guard.
--
-- The `clips` flag (0077) is all-or-nothing. A pilot needs "on, but only for
-- these vendors". This migration adds that, additively:
--
-- 1. `clip_pilot_vendors` — the allowlist. FORCE RLS; admin may READ it through
--    a client token, but there is NO client write grant: the only write path is
--    the admin API (`/admin/clips/pilot-vendors`, service role, audit_log row per
--    change).
--
-- 2. `platform_config.clip_pilot_allowlist_enforced` — `true` while the pilot
--    runs. Fail closed: a missing row, or any value other than JSON `false`,
--    means ENFORCED. Setting it to `false` ends the pilot (every KYC-verified
--    vendor may upload; every active vendor's published clips are public).
--
-- 3. `clip_vendor_in_pilot(vendor_id)` + a RESTRICTIVE select policy on
--    `video_clips` — so a direct PostgREST read obeys the same rule as the API:
--    a published clip from a vendor outside the allowlist is invisible to anon
--    and to every authenticated user except its owner and admins. Restrictive
--    policies AND with the existing permissive ones, so nothing that was hidden
--    becomes visible. Subqueries in the clip_products / clip_likes /
--    clip_comments public policies read video_clips under the caller's RLS, so
--    they inherit the gate.
--
-- 4. `clip_record_spend` re-arms after an operator reset. In 0079 the trip used
--    `coalesce(killed_at, now())`, so once a month had been tripped and reset,
--    later spend could never trip it again — the guard was silently off for the
--    rest of the month. Now: if the month is not currently killed (never
--    tripped, or reset since) and the new total reaches the cap, `killed_at`
--    moves to now(), which is newer than the reset and so closes the month
--    again. History is still non-destructive: `admin_reset_at` is kept.
--
-- Nothing here enables anything. `clips` stays false; the allowlist starts empty.
--
-- Down (reversible):
--   drop policy if exists video_clips_pilot_public_gate on public.video_clips;
--   drop function if exists public.clip_vendor_in_pilot(uuid);
--   drop table if exists public.clip_pilot_vendors;
--   delete from public.platform_config where key = 'clip_pilot_allowlist_enforced';
--   -- and re-run the clip_record_spend body from 0079_clip_cost_guard.sql.

-- ---------------------------------------------------------------------------
-- 1. Allowlist table
-- ---------------------------------------------------------------------------
create table public.clip_pilot_vendors (
  vendor_id uuid primary key references public.vendors (id) on delete cascade,
  note text check (note is null or char_length(note) <= 280),
  added_by uuid,
  created_at timestamptz not null default now()
);

comment on table public.clip_pilot_vendors is
  'Clips pilot allowlist. While platform_config.clip_pilot_allowlist_enforced is not false, only these vendors may upload clips and only their published clips are public. Written only by the admin API (audited).';

alter table public.clip_pilot_vendors enable row level security;
alter table public.clip_pilot_vendors force row level security;

create policy clip_pilot_vendors_admin_select
  on public.clip_pilot_vendors
  for select
  to authenticated
  using (public.has_role('admin'));

revoke all on table public.clip_pilot_vendors from anon, authenticated;
grant select on table public.clip_pilot_vendors to authenticated;
grant select, insert, update, delete on table public.clip_pilot_vendors to service_role;

-- ---------------------------------------------------------------------------
-- 2. Enforcement switch (fail closed)
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  (
    'clip_pilot_allowlist_enforced',
    'true'::jsonb,
    'Clips pilot gate. true (or missing / anything but JSON false) = only vendors in clip_pilot_vendors may upload and only their published clips are public; comments stay off. Set to false to end the pilot.'
  )
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- 3. Viewer gate for direct reads
-- ---------------------------------------------------------------------------
create or replace function public.clip_vendor_in_pilot(p_vendor_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    coalesce(
      (select pc.value = 'false'::jsonb
         from public.platform_config pc
        where pc.key = 'clip_pilot_allowlist_enforced'),
      false
    )
    or exists (
      select 1 from public.clip_pilot_vendors cpv
       where cpv.vendor_id = p_vendor_id
    );
$$;

comment on function public.clip_vendor_in_pilot(uuid) is
  'True when the Clips pilot gate is explicitly off (JSON false) or the vendor is allowlisted. Missing config = gate on (fail closed).';

revoke all on function public.clip_vendor_in_pilot(uuid) from public;
grant execute on function public.clip_vendor_in_pilot(uuid) to anon, authenticated, service_role;

create policy video_clips_pilot_public_gate
  on public.video_clips
  as restrictive
  for select
  using (
    status <> 'published'
    or public.clip_vendor_in_pilot(vendor_id)
    or public.has_role('admin')
    or exists (
      select 1 from public.vendors v
       where v.id = video_clips.vendor_id
         and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy video_clips_pilot_public_gate on public.video_clips is
  'Clips pilot: published clips are public only from allowlisted vendors (or once the pilot gate is off). Owners and admins are unaffected.';

-- ---------------------------------------------------------------------------
-- 4. Spend guard re-arms after a reset
-- ---------------------------------------------------------------------------
create or replace function public.clip_record_spend(
  p_month_key text,
  p_usd_micros bigint,
  p_clips integer,
  p_bytes bigint,
  p_cap_usd_micros bigint
)
returns bigint
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  new_total bigint;
begin
  if p_month_key !~ '^[0-9]{4}-[0-9]{2}$' then
    raise exception 'clip_record_spend: invalid month key %', p_month_key
      using errcode = 'check_violation';
  end if;

  insert into public.clip_spend_monthly (month_key, total_usd_micros, clips_transcoded, bytes_served)
  values (p_month_key, greatest(0, p_usd_micros), greatest(0, p_clips), greatest(0, p_bytes))
  on conflict (month_key) do update
    set total_usd_micros = public.clip_spend_monthly.total_usd_micros + greatest(0, p_usd_micros),
        clips_transcoded = public.clip_spend_monthly.clips_transcoded + greatest(0, p_clips),
        bytes_served = public.clip_spend_monthly.bytes_served + greatest(0, p_bytes)
  returning total_usd_micros into new_total;

  -- Trip when the cap is reached and the month is not already closed. "Closed"
  -- = killed_at set and not superseded by a later admin_reset_at. A reset month
  -- therefore re-trips on the next spend at/over the cap (raise the cap first).
  if p_cap_usd_micros > 0 and new_total >= p_cap_usd_micros then
    update public.clip_spend_monthly
       set killed_at = now()
     where month_key = p_month_key
       and (
         killed_at is null
         or (admin_reset_at is not null and admin_reset_at >= killed_at)
       );
  end if;

  return new_total;
end;
$$;

revoke all on function public.clip_record_spend(text, bigint, integer, bigint, bigint) from public;
grant execute on function public.clip_record_spend(text, bigint, integer, bigint, bigint) to service_role;
