# RLS isolation matrix (M03-P09)

```bash
supabase db start && supabase db reset
cd services/api && uv run pytest tests/rls -q
```

Requires a live Postgres reachable via `SUPABASE_DB_URL` or the default local stack URL `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.

## What this suite proves

- **Full matrix:** every `public` base table × six personas (`anon`, `customer`, `other_customer`, `vendor`, `other_vendor`, `admin`) × four verbs (`select`, `insert`, `update`, `delete`).
- **Schema drift guard:** `test_no_untested_tables` diffs `information_schema.tables` against the declarative `EXPECTATIONS` map — new migrations must add expectations.
- **Cross-tenant denials:** vendor B cannot read vendor A listings/payouts/quotes; customer B cannot read customer A orders/payments/invoices/addresses.
- **Service-role-only tables** (`notification_outbox`, `audit_log`, `user_roles`, `stock_reservations`, ledger internals) are client-invisible.

Role scoping uses `SET LOCAL role` + `SET LOCAL "request.jwt.claims"` inside rolled-back transactions (same pattern as pgTAP tests).

## Demo seed

From repo root:

```bash
python scripts/seed.py --env local
```

Idempotent upsert of browsable demo vendors, listings, events, services, and orders. Shared fixtures live in `services/api/tests/fixtures/demo/`.
