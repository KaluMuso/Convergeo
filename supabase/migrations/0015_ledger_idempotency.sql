-- M08-P05: ledger transaction idempotency key (additive, reversible).
-- Down (manual): drop index ledger_transactions_idempotency_key_key;
--                 alter table public.ledger_transactions drop column idempotency_key;

alter table public.ledger_transactions
  add column idempotency_key text;

create unique index ledger_transactions_idempotency_key_key
  on public.ledger_transactions (idempotency_key)
  where idempotency_key is not null;

comment on column public.ledger_transactions.idempotency_key is
  'Business-event idempotency key; partial unique index ensures at-most-once posting per key.';
