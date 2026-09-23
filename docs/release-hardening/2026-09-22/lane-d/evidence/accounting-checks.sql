SELECT jsonb_pretty(jsonb_build_object(
  'unbalanced_ledger_transactions', (
    SELECT count(*) FROM (
      SELECT t.id FROM public.ledger_transactions t
      JOIN public.ledger_postings p ON p.transaction_id = t.id
      GROUP BY t.id HAVING sum(p.amount_ngwee) <> 0
    ) unbalanced
  ),
  'checkouts_with_multiple_gross_receipts', (
    SELECT count(*) FROM (
      SELECT checkout_group_id FROM public.ledger_transactions
      WHERE kind IN ('charge_received', 'escrow_hold')
      GROUP BY checkout_group_id HAVING count(*) > 1
    ) duplicate_charge
  ),
  'pre_repair_wrong_amount_successes', (
    SELECT count(DISTINCT p.id)
    FROM public.payments p
    JOIN public.webhook_events w
      ON w.raw->'data'->>'reference' = p.lenco_reference
    JOIN public.ledger_transactions t ON t.payment_id = p.id
    WHERE p.status = 'success'
      AND w.raw->'data'->>'amount' = '1.00'
      AND w.processed_at IS NOT NULL
  ),
  'post_repair_wrong_amount_pending', (
    SELECT count(DISTINCT p.id)
    FROM public.payments p
    JOIN public.webhook_events w
      ON w.raw->'data'->>'reference' = p.lenco_reference
    WHERE p.status = 'ussd_pushed'
      AND w.raw->'data'->>'amount' = '1.00'
      AND w.processed_at IS NULL
      AND NOT EXISTS (
        SELECT 1 FROM public.ledger_transactions t WHERE t.payment_id = p.id
      )
  ),
  'cancelled_payments_with_gross_receipt', (
    SELECT count(DISTINCT p.id)
    FROM public.payments p
    JOIN public.ledger_transactions t ON t.payment_id = p.id
    WHERE p.status = 'cancelled'
      AND t.kind IN ('charge_received', 'escrow_hold')
  )
));
