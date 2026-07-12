-- M16-P09: Beta invite gate — invite codes with capacity + atomic, capacity-safe
-- redemption via a SECURITY DEFINER function, plus the flag that flips the gate
-- from invite-only to public with no deploy (feature_flags.public_launch).
--
-- Additive + reversible. RLS+FORCE on beta_invites: admin (has_role) may READ;
-- there is NO client insert/update/delete grant — the only client path that can
-- consume a slot is public.redeem_beta_invite (SECURITY DEFINER). Invite
-- management (create/list) runs server-side as service_role via the API.
--
-- capacity / used_count are plain counts (NOT money) — no ngwee semantics here.
--
-- Down (manual):
--   drop function if exists public.redeem_beta_invite(text);
--   drop table if exists public.beta_invites;
--   delete from public.feature_flags where flag = 'public_launch';

-- ---------------------------------------------------------------------------
-- beta_invites — invite codes gating pre-launch access. One row per code; a
-- code admits up to `capacity` redemptions. used_count is bounded to capacity by
-- a CHECK so a bug can never over-count even if the guarded UPDATE were bypassed.
-- ---------------------------------------------------------------------------
create table public.beta_invites (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (char_length(code) between 3 and 64),
  capacity integer not null check (capacity > 0),
  used_count integer not null default 0
    check (used_count >= 0 and used_count <= capacity),
  expires_at timestamptz,
  active boolean not null default true,
  note text check (note is null or char_length(note) <= 280),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index beta_invites_active_idx on public.beta_invites (active) where active;

create trigger beta_invites_set_updated_at
  before update on public.beta_invites
  for each row execute function public.set_updated_at();

comment on table public.beta_invites is
  'M16-P09 beta invite codes gating pre-launch access. capacity/used_count are counts (not money). Admin-managed server-side (service_role); redemption only via public.redeem_beta_invite (SECURITY DEFINER) — no client table write.';
comment on column public.beta_invites.used_count is
  'Slots consumed. CHECK used_count <= capacity is a hard backstop; the atomic guarded UPDATE in redeem_beta_invite prevents the over-capacity race in the first place.';

-- ---------------------------------------------------------------------------
-- Atomic, capacity-safe redemption. The guarded UPDATE increments used_count
-- only while the invite is active, in-capacity and unexpired. Under READ
-- COMMITTED, a concurrent txn that waited on the row lock re-evaluates the
-- WHERE against the freshly-incremented row, so the last slot is handed out
-- exactly once and losers fall through to the classification query -> 'exhausted'.
-- Returns a distinct outcome for every failure mode. SECURITY DEFINER: the sole
-- client path to consume a slot (callers have no direct table write).
-- ---------------------------------------------------------------------------
create or replace function public.redeem_beta_invite(p_code text)
returns table (outcome text, remaining integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.beta_invites;
begin
  update public.beta_invites
    set used_count = used_count + 1
  where code = p_code
    and active
    and used_count < capacity
    and (expires_at is null or expires_at > now())
  returning * into v_row;

  if found then
    outcome := 'redeemed';
    remaining := v_row.capacity - v_row.used_count;
    return next;
    return;
  end if;

  -- Not incremented: classify why so the caller can message the user distinctly.
  select * into v_row from public.beta_invites where code = p_code;
  if not found then
    outcome := 'invalid';
  elsif not v_row.active then
    outcome := 'inactive';
  elsif v_row.expires_at is not null and v_row.expires_at <= now() then
    outcome := 'expired';
  else
    outcome := 'exhausted';
  end if;
  remaining := 0;
  return next;
end;
$$;

comment on function public.redeem_beta_invite(text) is
  'M16-P09 atomic, capacity-safe beta invite redemption. Increments used_count only when active, in-capacity and unexpired; otherwise returns a distinct outcome (invalid/inactive/expired/exhausted). SECURITY DEFINER: only client path to consume a slot; no direct client table write.';

-- ---------------------------------------------------------------------------
-- public_launch feature flag — OFF at launch (invite-only). Flip ON to make the
-- gate a no-op (public) with no deploy. Seeded additively; leaves 0008 seeds intact.
-- ---------------------------------------------------------------------------
insert into public.feature_flags (flag, enabled, description) values
  (
    'public_launch',
    false,
    'M16-P09 beta gate — when ON, the beta invite gate is a no-op and the site is public (no deploy to flip).'
  )
on conflict (flag) do nothing;

-- ---------------------------------------------------------------------------
-- Row level security — admin read; service_role manages; NO client write grant.
-- ---------------------------------------------------------------------------
alter table public.beta_invites enable row level security;
alter table public.beta_invites force row level security;

create policy beta_invites_admin_select
  on public.beta_invites
  for select
  to authenticated
  using (public.has_role('admin'));

create policy beta_invites_service_role_all
  on public.beta_invites
  for all
  to service_role
  using (true)
  with check (true);

comment on policy beta_invites_admin_select on public.beta_invites is
  'Platform admins may read invite codes; all writes are service_role (API) or the SECURITY DEFINER redemption function.';
comment on policy beta_invites_service_role_all on public.beta_invites is
  'Invite management (create/list) runs server-side as service_role.';

-- Clients (authenticated/anon) get SELECT only — admins read; NO write grant, so
-- the only way to consume a slot is redeem_beta_invite (SECURITY DEFINER).
grant select on table public.beta_invites to authenticated;
grant select, insert, update, delete on table public.beta_invites to service_role;
grant execute on function public.redeem_beta_invite(text) to authenticated, anon, service_role;
