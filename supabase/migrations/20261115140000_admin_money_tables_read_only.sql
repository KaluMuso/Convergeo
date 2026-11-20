-- 2026-11 analytics/RBAC audit, finding S1.
--
-- The M03 policies `<table>_admin_all` (FOR ALL ... has_role('admin')) plus the
-- INSERT/UPDATE/DELETE grants held by `authenticated` let anyone with the `admin`
-- role write the money tables straight through PostgREST with their own browser
-- token: fabricate a balanced ledger transaction, delete ledger accounts, rewrite
-- a payment, payout or refund row. None of that passes the API's state machines,
-- payout guards, idempotency keys or audit_log.
--
-- Every legitimate writer of these six tables is the API (service_role) or a
-- SECURITY DEFINER function owned by the migration role; no application code
-- writes them with a user token, and the admin app never talks to the database
-- directly. So administrators keep their read access and lose the write path:
--   1. the admin policy becomes SELECT-only, and
--   2. the dead write grants are revoked from anon and authenticated, so no
--      future permissive policy can silently reopen the path.
-- Owner/customer/vendor SELECT policies and every service_role grant are untouched.
--
-- Down (manual, restores the previous posture exactly):
--   for each t in (ledger_accounts, ledger_transactions, ledger_postings,
--                  payments, payouts, refunds):
--     drop policy <t>_admin_select on public.<t>;
--     create policy <t>_admin_all on public.<t> for all to authenticated
--       using (public.has_role('admin')) with check (public.has_role('admin'));
--     grant insert, update, delete on public.<t> to authenticated;

do $$
declare
  t text;
begin
  foreach t in array array[
    'ledger_accounts', 'ledger_transactions', 'ledger_postings',
    'payments', 'payouts', 'refunds'
  ]
  loop
    execute format('drop policy if exists %I on public.%I', t || '_admin_all', t);
    execute format('drop policy if exists %I on public.%I', t || '_admin_select', t);
    execute format(
      'create policy %I on public.%I for select to authenticated '
      'using (public.has_role(''admin''))',
      t || '_admin_select', t
    );
    execute format(
      'comment on policy %I on public.%I is %L',
      t || '_admin_select', t,
      'Platform admins may read; writes are service_role only (2026-11 RBAC audit S1).'
    );
    execute format(
      'revoke insert, update, delete, truncate, references, trigger on public.%I '
      'from anon, authenticated',
      t
    );
  end loop;
end
$$;
