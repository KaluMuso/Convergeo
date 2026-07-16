-- Events Phase-2 Wave A / M10-P12 (decision D29): ticket pricing modes.
--
-- Two organiser-configurable discounts on top of a ticket_type's base
-- price_ngwee, both resolved SERVER-SIDE at checkout (services/tickets/purchase.py)
-- — the client never supplies a price:
--   * Early-bird: a lower per-unit price until a cutoff time.
--       ticket_types.early_bird_price_ngwee + ticket_types.early_bird_until
--       (both-or-neither). Active while now < early_bird_until.
--   * Group/tiered: a lower per-unit price at or above a quantity threshold.
--       ticket_type_price_tiers(ticket_type_id, min_qty, price_ngwee).
--
-- Resolution is "buyer gets the lowest applicable price" (base, active early-bird,
-- and every qualifying tier are candidates; the minimum wins) — deterministic and
-- unmanipulable. Absence of any early-bird/tier config = today's flat base price,
-- so this migration is purely additive and changes nothing until an organiser
-- configures a discount.
--
-- Additive + reversible. Down:
--   alter table public.ticket_types drop constraint ticket_types_early_bird_pair_chk;
--   alter table public.ticket_types drop column early_bird_price_ngwee,
--     drop column early_bird_until;
--   drop table public.ticket_type_price_tiers;  -- cascades policies

alter table public.ticket_types
  add column early_bird_price_ngwee bigint
    check (early_bird_price_ngwee is null or early_bird_price_ngwee >= 0);

alter table public.ticket_types
  add column early_bird_until timestamptz;

-- Both-or-neither: an early-bird price is meaningless without a cutoff, and vice versa.
alter table public.ticket_types
  add constraint ticket_types_early_bird_pair_chk
  check ((early_bird_price_ngwee is null) = (early_bird_until is null));

comment on column public.ticket_types.early_bird_price_ngwee is
  'Optional discounted per-unit price (ngwee) active until early_bird_until. '
  'Resolved server-side at checkout; NULL = no early-bird.';
comment on column public.ticket_types.early_bird_until is
  'Cutoff after which the early-bird price stops applying. Paired with '
  'early_bird_price_ngwee (both set or both NULL).';

create table public.ticket_type_price_tiers (
  ticket_type_id uuid not null references public.ticket_types (id) on delete cascade,
  min_qty int not null check (min_qty >= 2),
  price_ngwee bigint not null check (price_ngwee >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (ticket_type_id, min_qty)
);

comment on table public.ticket_type_price_tiers is
  'Group/bulk per-unit pricing (M10-P12): buying >= min_qty of this type resolves '
  'to price_ngwee per unit. min_qty >= 2 (qty 1 is the base price). The lowest '
  'qualifying tier wins, server-side.';

-- RLS: public read only when the parent event is published (the purchase UI shows
-- tier pricing); organisers manage tiers for events they own; admins all. Mirrors
-- public.ticket_type_instances (0048). Writes flow through the service role in the
-- organiser API; policies keep client access correct in depth.
alter table public.ticket_type_price_tiers enable row level security;

create policy ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers
  for select
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and e.status = 'published'
    )
  );

create policy ticket_type_price_tiers_organiser_select
  on public.ticket_type_price_tiers
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_price_tiers_organiser_insert
  on public.ticket_type_price_tiers
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_price_tiers_organiser_update
  on public.ticket_type_price_tiers
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_price_tiers_organiser_delete
  on public.ticket_type_price_tiers
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_price_tiers_admin_all
  on public.ticket_type_price_tiers
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

grant select, insert, update, delete
  on table public.ticket_type_price_tiers to authenticated, service_role;
grant select on table public.ticket_type_price_tiers to anon;
