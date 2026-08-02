-- B0-P02a — cart line prices become server-controlled at the database.
--
-- THE HOLE THIS CLOSES (B2B audit G3, 2026-08-01): cart_items grants INSERT
-- and UPDATE to `authenticated` and `anon` (0012), and the owner policies gate
-- ROWS, not COLUMNS. Any cart owner could therefore write their own
-- unit_price_ngwee or wholesale flag through PostgREST, bypassing the API
-- entirely — and checkout consumed the stored values as given. Combined with
-- the tier logic this priced orders at whatever the client claimed.
--
-- THE FIX, decided by the founder on 2026-08-02 ("pin columns to
-- service-role"): revoke client INSERT/UPDATE on cart_items outright. Line
-- writes happen only through the API's service-role client, where price and
-- wholesale are derived by the one implementation of the tier rules
-- (services/cart/totals.py + merge.py) from the listing and the caller's
-- verified-business eligibility. No SQL re-implementation of money logic —
-- CLAUDE.md convention 1 is exactly about not having two.
--
-- Why revoke, not a guard trigger like 0038/0084: those guards exist because
-- admins legitimately write the guarded tables through PostgREST with an
-- `authenticated` JWT, so the distinction must be made per-request inside the
-- trigger. Nobody legitimately writes cart LINES client-side — the API owns
-- every insert and every qty change (it must re-derive price on both). A
-- privilege is checked before RLS, costs nothing per row, and cannot be
-- bypassed by a path that forgets to attach a trigger.
--
-- What clients KEEP:
--   * SELECT — the cart renders from the owner/guest RLS policies unchanged.
--   * DELETE — removing a line moves no money; owner/guest delete policies
--     still scope rows.
-- The INSERT/UPDATE row policies from 0012 are left in place, inert. They
-- document the ownership predicate and become live again if a future decision
-- re-grants a column subset (e.g. qty-only client updates).
--
-- Reversible: `grant insert, update on public.cart_items to authenticated,
-- anon;` restores 0012's posture exactly.

revoke insert, update on table public.cart_items from authenticated, anon;

comment on column public.cart_items.unit_price_ngwee is
  'Integer ngwee. Server-derived from the listing + tier rules + buyer eligibility; client INSERT/UPDATE on cart_items is revoked (0086), so this can only be written by the service role via the API.';
comment on column public.cart_items.wholesale is
  'Server-derived: listing.wholesale AND verified-business eligibility, never trusted from the client (0086). Under D36 a non-eligible buyer''s wholesale-only line is dropped, not re-priced.';

-- Fail the migration itself if the revoke did not take (e.g. a future
-- migration re-granted more broadly first and ordering changes).
do $$
declare
  leak int;
begin
  select count(*) into leak
  from information_schema.role_table_grants
  where table_schema = 'public'
    and table_name = 'cart_items'
    and grantee in ('authenticated', 'anon')
    and privilege_type in ('INSERT', 'UPDATE');
  if leak > 0 then
    raise exception 'cart_items still grants INSERT/UPDATE to client roles (% rows) — 0086 did not take effect', leak;
  end if;
end $$;
