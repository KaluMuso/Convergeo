-- M18-P01 — WAHA vendor-intake durable model (D35).
--
-- Seven additive tables that hold everything the intake lane needs and nothing
-- it must not have. FORCE RLS on every one; anon reads nothing anywhere in this
-- mountain.
--
-- Deliberate design notes:
--
-- * The intake identity is a DEDICATED binding, not vendors.whatsapp_msisdn.
--   That column (0046) is the PUBLIC storefront "Chat on WhatsApp" contact
--   number. Overloading it would mean disenrolling from intake blanks a
--   vendor's storefront link, and would stop a vendor publishing one number
--   while messaging from another. The binding is reversible by design.
--
-- * A phone maps to exactly ONE active verified vendor BY CONSTRAINT (a unique
--   partial index), not by a query the application must remember to write.
--   Ambiguity is therefore impossible rather than merely unlikely.
--
-- * intake_events is APPEND-ONLY: no update or delete policy exists for any
--   role, so the audit trail cannot be rewritten from the application.
--
-- * Raw message content carries purge_after so the M18-P07 retention sweep can
--   minimise it on a short window (D35 §12) without touching dispositions.
--
-- * NOTHING here references or writes vendor_listings. Under the corrected D35
--   only M18-P05's guarded, vendor-confirmed handoff may do that.
--
-- Reversible: drop the tables in reverse dependency order.

-- ---------------------------------------------------------------------------
-- Enrollment: reversible vendor <-> phone binding with explicit opt-in
-- ---------------------------------------------------------------------------
create table public.intake_vendor_bindings (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  -- E.164 digits, no plus — same normalised shape as vendors.whatsapp_msisdn.
  msisdn text not null check (msisdn ~ '^260[79][0-9]{8}$'),
  opted_in_at timestamptz not null default now(),
  opted_out_at timestamptz,
  consent_source text not null check (consent_source in ('vendor_app', 'agreement_clause')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- The invariant that makes "known verified sender" unambiguous: at most one
-- ACTIVE binding per phone number, enforced by the database.
create unique index intake_vendor_bindings_active_msisdn_uniq
  on public.intake_vendor_bindings (msisdn)
  where opted_out_at is null;

create index intake_vendor_bindings_vendor_idx
  on public.intake_vendor_bindings (vendor_id, opted_out_at);

create trigger intake_vendor_bindings_set_updated_at
  before update on public.intake_vendor_bindings
  for each row execute function public.set_updated_at();

comment on table public.intake_vendor_bindings is
  'D35 intake enrollment: reversible, opt-in binding of a vendor to the MSISDN they message from. '
  'Distinct from vendors.whatsapp_msisdn (the public storefront contact number).';

-- ---------------------------------------------------------------------------
-- Sessions: one per in-flight intake conversation
-- ---------------------------------------------------------------------------
create table public.intake_sessions (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  binding_id uuid not null references public.intake_vendor_bindings (id) on delete restrict,
  status text not null default 'collecting' check (
    status in (
      'collecting',
      'needs_details',
      'ready_for_vendor_review',
      'submitted',
      'pending_admin_review',
      'approved',
      'rejected',
      'expired'
    )
  ),
  -- Structured, i18n-keyed follow-up requests. The lane is strictly
  -- inbound-only: these are DATA rendered by the vendor app (M18-P05), never
  -- a message sent to the vendor.
  pending_requests jsonb not null default '[]'::jsonb,
  rejection_reason text,
  last_activity_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '14 days'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index intake_sessions_vendor_status_idx
  on public.intake_sessions (vendor_id, status, last_activity_at desc);

create index intake_sessions_status_expiry_idx
  on public.intake_sessions (status, expires_at);

create trigger intake_sessions_set_updated_at
  before update on public.intake_sessions
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Inbound messages: idempotency + minimised, short-retention raw content
-- ---------------------------------------------------------------------------
create table public.intake_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.intake_sessions (id) on delete cascade,
  -- The signed WAHA message id. UNIQUE is the replay guarantee at the domain
  -- layer; webhook_events (provider,event_id) guards the transport layer.
  provider_message_id text not null unique,
  kind text not null check (kind in ('text', 'image', 'mixed', 'unsupported')),
  -- Minimised excerpt only — never a full transcript, never a free-floating
  -- phone log (the vendor is referenced through the session/binding).
  raw_excerpt text,
  received_at timestamptz not null default now(),
  purge_after timestamptz not null default (now() + interval '30 days')
);

create index intake_messages_session_idx
  on public.intake_messages (session_id, received_at desc);

create index intake_messages_purge_idx
  on public.intake_messages (purge_after)
  where raw_excerpt is not null;

comment on column public.intake_messages.purge_after is
  'D35 §12 retention: the M18-P07 sweep nulls raw_excerpt past this instant, keeping IDs/dispositions.';

-- ---------------------------------------------------------------------------
-- Media: references only. Bytes live in the private storage bucket (M18-P03).
-- ---------------------------------------------------------------------------
create table public.intake_media (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.intake_sessions (id) on delete cascade,
  storage_path text not null,
  content_hash text not null,
  byte_size bigint not null check (byte_size > 0),
  mime_type text not null check (mime_type in ('image/jpeg', 'image/png', 'image/webp')),
  width_px integer check (width_px > 0),
  height_px integer check (height_px > 0),
  fetched_at timestamptz not null default now(),
  -- Same-image dedupe within a session: one stored object, one row.
  unique (session_id, content_hash)
);

create index intake_media_session_idx on public.intake_media (session_id);

-- ---------------------------------------------------------------------------
-- Draft fields: the structured product data, one row per session
-- ---------------------------------------------------------------------------
create table public.intake_draft_fields (
  session_id uuid primary key references public.intake_sessions (id) on delete cascade,
  title text,
  category_id uuid references public.categories (id) on delete set null,
  -- Money is integer ngwee. Never numeric, never float.
  price_ngwee bigint check (price_ngwee is null or price_ngwee >= 0),
  pricing_mode text check (pricing_mode is null or pricing_mode in ('fixed', 'negotiable', 'tiered')),
  quantity integer check (quantity is null or quantity >= 0),
  stock_mode text check (stock_mode is null or stock_mode in ('tracked', 'made_to_order', 'always')),
  sale_unit text,
  condition text check (condition is null or condition in ('new', 'refurbished', 'used')),
  description text,
  specifications jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger intake_draft_fields_set_updated_at
  before update on public.intake_draft_fields
  for each row execute function public.set_updated_at();

comment on column public.intake_draft_fields.price_ngwee is
  'Integer ngwee (K1,234.56 = 123456). Parsed via Decimal only — float on money is a bug.';

-- ---------------------------------------------------------------------------
-- Provenance: what a machine guessed vs what the human typed
-- ---------------------------------------------------------------------------
create table public.intake_field_provenance (
  session_id uuid not null references public.intake_sessions (id) on delete cascade,
  field_name text not null,
  source text not null check (source in ('vendor_typed', 'rule', 'model')),
  confidence numeric(4, 3) check (confidence is null or (confidence >= 0 and confidence <= 1)),
  model_ref text,
  recorded_at timestamptz not null default now(),
  primary key (session_id, field_name)
);

comment on table public.intake_field_provenance is
  'Per-field origin so a human reviewer always sees which values a machine suggested. '
  'A vendor correction flips the row to vendor_typed.';

-- ---------------------------------------------------------------------------
-- Events: append-only audit trail with the D35 §11 disposition taxonomy
-- ---------------------------------------------------------------------------
-- Two kinds of thing are worth auditing and they are NOT the same shape:
--   * 'ingestion' — what happened to an inbound WAHA event (the D35 §11
--     disposition taxonomy). Often has no session and no resolvable vendor.
--   * 'transition' — a guarded session state change (convention #4). Always has
--     a session and a from/to pair, and no disposition applies.
-- Collapsing them into one enum would force meaningless dispositions onto
-- transitions, so the shape is discriminated and each kind's required columns
-- are enforced by CHECK rather than by convention.
create table public.intake_events (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('ingestion', 'transition')),
  -- Nullable: a dropped event may have no resolvable vendor, and recording a
  -- guess would defeat the no-account-disclosure rule.
  vendor_id uuid references public.vendors (id) on delete set null,
  session_id uuid references public.intake_sessions (id) on delete set null,
  provider_event_id text,
  disposition text check (
    disposition in (
      'draft_created',
      'dropped_group',
      'dropped_unverified',
      'dropped_flag_off',
      'rejected_auth',
      'error'
    )
  ),
  from_status text,
  to_status text,
  message_kind text,
  detail jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  constraint intake_events_shape_ck check (
    (kind = 'ingestion' and disposition is not null and to_status is null)
    or (kind = 'transition' and session_id is not null and to_status is not null)
  )
);

create index intake_events_disposition_idx
  on public.intake_events (disposition, occurred_at desc)
  where kind = 'ingestion';

create index intake_events_session_idx
  on public.intake_events (session_id, occurred_at desc);

comment on table public.intake_events is
  'Append-only D35 §11 audit trail. No UPDATE/DELETE policy exists for any role.';

-- ---------------------------------------------------------------------------
-- RLS — FORCE on every table; anon reads nothing; vendors see only their own.
-- ---------------------------------------------------------------------------
alter table public.intake_vendor_bindings enable row level security;
alter table public.intake_vendor_bindings force row level security;
alter table public.intake_sessions enable row level security;
alter table public.intake_sessions force row level security;
alter table public.intake_messages enable row level security;
alter table public.intake_messages force row level security;
alter table public.intake_media enable row level security;
alter table public.intake_media force row level security;
alter table public.intake_draft_fields enable row level security;
alter table public.intake_draft_fields force row level security;
alter table public.intake_field_provenance enable row level security;
alter table public.intake_field_provenance force row level security;
alter table public.intake_events enable row level security;
alter table public.intake_events force row level security;

-- Bindings: the owning vendor may read and may opt out (update); inserts are
-- service-role only so enrollment always goes through the audited flow.
create policy intake_vendor_bindings_owner_select
  on public.intake_vendor_bindings
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = intake_vendor_bindings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_vendor_bindings_owner_update
  on public.intake_vendor_bindings
  for update
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = intake_vendor_bindings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = intake_vendor_bindings.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_vendor_bindings_admin_all
  on public.intake_vendor_bindings
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Sessions: owner reads and updates its own; admin all.
create policy intake_sessions_owner_select
  on public.intake_sessions
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = intake_sessions.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_sessions_owner_update
  on public.intake_sessions
  for update
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = intake_sessions.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = intake_sessions.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_sessions_admin_all
  on public.intake_sessions
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Child tables: readable by the owner of the parent session; admin all.
-- Writes are service-role only (the ingestion path), so no insert policy.
create policy intake_messages_owner_select
  on public.intake_messages
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.intake_sessions s
      join public.vendors v on v.id = s.vendor_id
      where s.id = intake_messages.session_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_messages_admin_all
  on public.intake_messages
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy intake_media_owner_select
  on public.intake_media
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.intake_sessions s
      join public.vendors v on v.id = s.vendor_id
      where s.id = intake_media.session_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_media_admin_all
  on public.intake_media
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy intake_draft_fields_owner_select
  on public.intake_draft_fields
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.intake_sessions s
      join public.vendors v on v.id = s.vendor_id
      where s.id = intake_draft_fields.session_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_draft_fields_owner_update
  on public.intake_draft_fields
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.intake_sessions s
      join public.vendors v on v.id = s.vendor_id
      where s.id = intake_draft_fields.session_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.intake_sessions s
      join public.vendors v on v.id = s.vendor_id
      where s.id = intake_draft_fields.session_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_draft_fields_admin_all
  on public.intake_draft_fields
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy intake_field_provenance_owner_select
  on public.intake_field_provenance
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.intake_sessions s
      join public.vendors v on v.id = s.vendor_id
      where s.id = intake_field_provenance.session_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy intake_field_provenance_admin_all
  on public.intake_field_provenance
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

-- Events: append-only. Admin may SELECT; nobody gets UPDATE or DELETE, and the
-- only writer is the service role (which bypasses RLS). Deliberately there is
-- no vendor read policy: dispositions include drops for numbers we could not
-- resolve, and exposing them would leak enrollment state.
create policy intake_events_admin_select
  on public.intake_events
  for select
  to authenticated
  using (public.has_role('admin'));

-- ---------------------------------------------------------------------------
-- Grants — service_role ONLY. No client role can reach these tables at all.
--
-- The vendor review page (M18-P05) and admin queue (M18-P06) read through the
-- FastAPI API, not PostgREST, so no client GRANT is needed. Withholding it
-- makes the intake tables invisible to anon and to every authenticated role by
-- privilege, independently of RLS.
--
-- The owner/admin policies above are therefore defence-in-depth: they are the
-- second lock, correct and tested, so that if a future pebble ever does grant a
-- client role access it inherits per-vendor isolation instead of a wide-open
-- table. Policy without grant is safe; grant without policy is not.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on table public.intake_vendor_bindings to service_role;
grant select, insert, update, delete on table public.intake_sessions to service_role;
grant select, insert, update, delete on table public.intake_messages to service_role;
grant select, insert, update, delete on table public.intake_media to service_role;
grant select, insert, update, delete on table public.intake_draft_fields to service_role;
grant select, insert, update, delete on table public.intake_field_provenance to service_role;
-- Append-only: the service role may read and insert, never update or delete.
grant select, insert on table public.intake_events to service_role;
