-- Pilot money fix: the customer's delivery fee is platform revenue, not vendor money.
--
-- Background: escrow release (services/escrow/release.py) and COD collection
-- (services/payments/cod.py) used to release items + delivery fee − commission
-- to the vendor, although the platform books and pays the courier (D16). The API
-- now captures the fee from escrow with the `delivery_fee_capture` template
-- (debit escrow, credit delivery_revenue) and releases items − commission only.
--
-- This migration:
--   1. Widens the ledger_accounts.kind check (0006_money.sql) with
--      'delivery_revenue' (platform account, vendor_id IS NULL).
--   2. Seeds the platform `delivery_revenue` account with a deterministic id,
--      following 20261107130000_seed_ledger_accounts.sql.
--
-- Additive only and idempotent (`on conflict do nothing`; the constraint is
-- dropped/re-added with a strict superset of the old list).
--
-- Down (manual, only while no posting references the account — ledger_postings
-- has ON DELETE RESTRICT, so this fails closed once money has moved):
--   delete from public.ledger_accounts
--   where kind = 'delivery_revenue' and vendor_id is null
--     and not exists (select 1 from public.ledger_postings lp where lp.account_id = ledger_accounts.id);
--   alter table public.ledger_accounts drop constraint ledger_accounts_kind_check;
--   alter table public.ledger_accounts add constraint ledger_accounts_kind_check
--     check (kind in ('platform_cash', 'escrow', 'commission_revenue',
--                     'vendor_payable', 'cod_receivable', 'fees'));

alter table public.ledger_accounts drop constraint if exists ledger_accounts_kind_check;
alter table public.ledger_accounts add constraint ledger_accounts_kind_check
  check (kind in (
    'platform_cash', 'escrow', 'commission_revenue',
    'vendor_payable', 'cod_receivable', 'fees',
    'delivery_revenue'
  ));

insert into public.ledger_accounts (id, kind)
values ('c7000000-0000-0000-0000-000000000007', 'delivery_revenue')
on conflict (kind) where vendor_id is null do nothing;
