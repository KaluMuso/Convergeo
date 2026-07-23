-- ledger-invariants.sql — read-only money integrity checks (VB-P01…P06 / F9b S1–S3).
--
-- Run after each money-drill stage against the isolated staging DB:
--   psql -v ON_ERROR_STOP=1 "$SUPABASE_DB_URL" -f scripts/db/ledger-invariants.sql
--
-- Emits violation rows (if any) then raises on failure. No secrets; no writes.
-- Complements load/invariant-check.py (oversell + invoice gapless).

\set ON_ERROR_STOP on

\echo '==> ledger-invariants: per-transaction zero-sum'
SELECT 'txn_imbalance' AS check_name,
       lp.transaction_id::text AS entity_id,
       sum(lp.amount_ngwee)::bigint AS imbalance_ngwee
FROM public.ledger_postings lp
GROUP BY lp.transaction_id
HAVING sum(lp.amount_ngwee) <> 0;

\echo '==> ledger-invariants: system-wide balance'
SELECT 'system_imbalance' AS check_name,
       NULL::text AS entity_id,
       coalesce(sum(amount_ngwee), 0)::bigint AS imbalance_ngwee
FROM public.ledger_postings
HAVING coalesce(sum(amount_ngwee), 0) <> 0;

\echo '==> ledger-invariants: orphan transactions (no postings)'
SELECT 'orphan_transaction' AS check_name,
       lt.id::text AS entity_id,
       0::bigint AS imbalance_ngwee
FROM public.ledger_transactions lt
WHERE NOT EXISTS (
  SELECT 1 FROM public.ledger_postings lp WHERE lp.transaction_id = lt.id
);

\echo '==> ledger-invariants: orphan postings (missing account)'
SELECT 'orphan_posting_account' AS check_name,
       lp.id::text AS entity_id,
       lp.amount_ngwee AS imbalance_ngwee
FROM public.ledger_postings lp
LEFT JOIN public.ledger_accounts la ON la.id = lp.account_id
WHERE la.id IS NULL;

\echo '==> ledger-invariants: escrow account snapshot (informational)'
SELECT 'escrow_balance' AS check_name,
       la.id::text AS entity_id,
       coalesce(sum(lp.amount_ngwee), 0)::bigint AS imbalance_ngwee
FROM public.ledger_accounts la
LEFT JOIN public.ledger_postings lp ON lp.account_id = la.id
WHERE la.kind = 'escrow' AND la.vendor_id IS NULL
GROUP BY la.id;

DO $invariants$
DECLARE
  txn_bad bigint;
  sys_bad bigint;
  orphan_txn bigint;
  orphan_acct bigint;
BEGIN
  SELECT count(*) INTO txn_bad
  FROM (
    SELECT transaction_id
    FROM public.ledger_postings
    GROUP BY transaction_id
    HAVING sum(amount_ngwee) <> 0
  ) t;

  SELECT CASE WHEN coalesce(sum(amount_ngwee), 0) <> 0 THEN 1 ELSE 0 END
    INTO sys_bad
  FROM public.ledger_postings;

  SELECT count(*) INTO orphan_txn
  FROM public.ledger_transactions lt
  WHERE NOT EXISTS (
    SELECT 1 FROM public.ledger_postings lp WHERE lp.transaction_id = lt.id
  );

  SELECT count(*) INTO orphan_acct
  FROM public.ledger_postings lp
  LEFT JOIN public.ledger_accounts la ON la.id = lp.account_id
  WHERE la.id IS NULL;

  IF txn_bad > 0 OR sys_bad > 0 OR orphan_txn > 0 OR orphan_acct > 0 THEN
    RAISE EXCEPTION
      'LEDGER INVARIANTS FAIL: txn_imbalance=% system_imbalance=% orphan_txn=% orphan_acct=%',
      txn_bad, sys_bad, orphan_txn, orphan_acct;
  END IF;

  RAISE NOTICE 'LEDGER INVARIANTS PASS: zero-sum per txn, system balanced, no orphan legs';
END;
$invariants$;
