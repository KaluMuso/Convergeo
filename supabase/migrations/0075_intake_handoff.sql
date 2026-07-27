-- M18-P05/P06 — vendor review handoff + admin publication control (D35).
--
-- Additive only (convention #6). Two things are added:
--
-- 1. The **handoff link** on intake_sessions. A submitted intake draft becomes a
--    normal vendor_listings row through the existing M12-P03 creation seam; the
--    session keeps a pointer to it so provenance survives the handoff. The FK is
--    `on delete set null`: removing a listing must never cascade away the audit
--    trail of how it was created.
--
-- 2. `intake_deep_links` — single-use, short-TTL, session-scoped tokens for the
--    review page.
--
--    IMPORTANT: the token is **not** the authorisation. Redemption still
--    requires an authenticated vendor session AND ownership of the intake
--    session; the token only names *which* session the vendor is opening and
--    proves the link was minted by us. A stolen link is therefore useless
--    without the vendor's own login.
--
--    Only the SHA-256 hash of the token is stored, so a database read cannot
--    reconstruct a usable link — the same posture as any password-equivalent.
--
--    Delivery is **Lane 1 only** (official Cloud API / outbox) or in-app. The
--    WAHA lane is strictly inbound-only and may never carry this link.
--
-- Reversible: drop intake_deep_links, drop the three columns.

alter table public.intake_sessions
  add column if not exists listing_id uuid
    references public.vendor_listings (id) on delete set null,
  add column if not exists submitted_at timestamptz,
  add column if not exists admin_notes text;

create index if not exists intake_sessions_listing_idx
  on public.intake_sessions (listing_id)
  where listing_id is not null;

comment on column public.intake_sessions.listing_id is
  'The vendor_listings row this intake produced (M18-P05 handoff). Provenance stays queryable '
  'from the listing back through the session to intake_field_provenance.';

-- ---------------------------------------------------------------------------
-- Deep links: single-use, short-TTL, session-scoped. Never the authorisation.
-- ---------------------------------------------------------------------------
create table public.intake_deep_links (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.intake_sessions (id) on delete cascade,
  -- SHA-256 of the token. The plaintext is returned once, at mint time, and is
  -- never persisted anywhere.
  token_hash text not null unique,
  expires_at timestamptz not null,
  redeemed_at timestamptz,
  created_at timestamptz not null default now()
);

create index intake_deep_links_session_idx
  on public.intake_deep_links (session_id, created_at desc);

-- Sweep support for M18-P07: expired-and-unredeemed rows are disposable.
create index intake_deep_links_expiry_idx
  on public.intake_deep_links (expires_at)
  where redeemed_at is null;

comment on table public.intake_deep_links is
  'Single-use short-TTL review links. Only a SHA-256 hash is stored. Redemption additionally '
  'requires an authenticated vendor who owns the session — the token alone authorises nothing.';

alter table public.intake_deep_links enable row level security;
alter table public.intake_deep_links force row level security;

-- No client policy at all. A vendor never needs to read link rows: they mint
-- and redeem through the API, which uses the service role. Admin gets SELECT
-- for incident review only — never the plaintext, which does not exist here.
create policy intake_deep_links_admin_select
  on public.intake_deep_links
  for select
  to authenticated
  using (public.has_role('admin'));

-- Grants — service_role only, matching 0073. Policy without grant is safe;
-- grant without policy is not.
grant select, insert, update, delete on table public.intake_deep_links to service_role;
