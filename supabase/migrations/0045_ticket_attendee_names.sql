-- Events Phase-2 Wave A / M10-P11 (decision D29): per-attendee ticket data.
--
-- Adds optional attendee identity so named/allocated tickets (pop-up dinners,
-- comedy, allocated seating) can carry a name per ticket:
--   * tickets.holder_name — the per-attendee name; NULL when not collected.
--   * ticket_types.attendee_named — organiser flag; when true, buyers must
--     supply one name per ticket at purchase.
--   * order_item_tickets.attendee_names — jsonb array of the names captured at
--     checkout, carried to (async) issuance where each lands on a
--     tickets.holder_name.
--
-- Names are written server-side only (clients cannot write tickets; the guard
-- trigger blocks client ticket INSERT/UPDATE) and are captured through the
-- purchase API. Additive + non-breaking (nullable / default false). Down:
--   alter table public.tickets drop column holder_name;
--   alter table public.ticket_types drop column attendee_named;
--   alter table public.order_item_tickets drop column attendee_names;

alter table public.tickets
  add column holder_name text;

alter table public.ticket_types
  add column attendee_named boolean not null default false;

alter table public.order_item_tickets
  add column attendee_names jsonb;

comment on column public.tickets.holder_name is
  'Optional per-attendee name (Wave A/M10-P11). Server-written from the purchase '
  'API; NULL when not collected.';
comment on column public.ticket_types.attendee_named is
  'When true, buyers must provide one attendee name per ticket at purchase '
  '(pop-up dinners, allocated seating).';
comment on column public.order_item_tickets.attendee_names is
  'JSON array of attendee names captured at checkout, carried to issuance where '
  'each name lands on a ticket.holder_name (by ticket creation order).';
