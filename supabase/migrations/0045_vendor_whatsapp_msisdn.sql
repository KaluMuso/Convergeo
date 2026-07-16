-- 0045: Vendor WhatsApp contact number.
--
-- (Renumbered 0042 → 0045: this migration and 0042_ticket_attendee_names both merged
--  claiming version 0042 — a duplicate version prefix that breaks `supabase db start`
--  (schema_migrations PK, SQLSTATE 23505) and reddens the db/rls CI jobs on master.
--  With 0043_harden and 0044_product_description ahead of it, this independent vendor
--  migration moves to the next free slot; body unchanged.)
--
-- Vergeo5 is WhatsApp-native (Zambia guardrails), but the public vendor storefront
-- had no way for a shopper to reach a seller directly. This adds an optional
-- contact WhatsApp number, distinct from `payout_msisdn` (the money rail): it is a
-- public "Chat on WhatsApp" contact surfaced on the vendor detail page as a wa.me
-- deep link.
--
-- Stored canonically as E.164 digits without '+' (260 + 9-digit Zambian mobile),
-- so the frontend can build https://wa.me/<msisdn> directly. The API normalises
-- input (0977…, +260…, 977…) to this form; the CHECK enforces it as defence in
-- depth. Zambian mobile subscriber numbers start with 7 or 9 (07x / 09x).
--
-- Additive, nullable (safe after M03). Existing rows stay NULL. Inherits the
-- vendors table RLS — no policy change.
--
-- Reversible: `alter table public.vendors drop column whatsapp_msisdn;`

alter table public.vendors
  add column if not exists whatsapp_msisdn text;

alter table public.vendors
  drop constraint if exists vendors_whatsapp_msisdn_check;

alter table public.vendors
  add constraint vendors_whatsapp_msisdn_check
  check (
    whatsapp_msisdn is null
    or whatsapp_msisdn ~ '^260[79][0-9]{8}$'
  );

comment on column public.vendors.whatsapp_msisdn is
  'Public contact WhatsApp number as E.164 digits (260 + 9-digit Zambian mobile). NULL until set. Distinct from payout_msisdn (money rail).';
