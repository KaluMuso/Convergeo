# Migration plan — live vs master tip (2026-07-20)

Companion to `deploy-migration-truth.md`. **Not executed.**

## Unapplied (content)

1. **FORCE RLS on launch tables** — repo `supabase/migrations/0064_force_rls_launch_tables.sql` (PR #367)
2. **`refunds.source_key` uniqueness** — repo `supabase/migrations/0065_refunds_source_key_uniq.sql` (PR #352 body, RC-02 renumber)

## Live ledger entry represented by RC-02

- `0063_revoke_execute_review_reply_guards` (applied `20260720074318`) — RC-02 adds the matching repo file from `claude/convergeo-bug-audit-nu1g4b`.

## Recommended sequence

1. Verify recoverable backup (OCI dump object name + date, or dashboard backup id).
2. Merge RC-02 reconcile:
   - Add `0063_revoke_execute_review_reply_guards.sql` (identical to live).
   - Keep `0064_force_rls_launch_tables.sql` as-is.
   - Renumber source_key file to **`0065_…`** because `0064` is already FORCE RLS on master.
3. Apply FORCE RLS migration.
4. Apply source_key migration (empty `refunds` → low risk).
5. Run verification queries from `deploy-migration-truth.md` §5.
6. Repair API host + promote frontends to master tip.
7. Only then reconsider G9 evidence — still needs rollback drill for full PASS.

## Per-migration detail

### A. FORCE RLS (#367 body)

- **Txn:** one migration
- **Locks:** brief on three tables
- **Backfill:** none
- **Rollback:** `NO FORCE ROW LEVEL SECURITY` on each
- **Verify:**

```sql
SELECT relname, relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public'
  AND relname IN (
    'ticket_type_instances','ticket_type_price_tiers','product_relations'
  );
-- expect all relforcerowsecurity = true
```

### B. source_key (#352 body)

- **Txn:** one migration
- **Locks:** ALTER + CREATE INDEX on `public.refunds`
- **Backfill:** UPDATE all null `source_key` (0 rows today)
- **Guard:** DO block aborts if duplicate active source_keys
- **Rollback:** drop `refunds_source_key_active_uniq` + column; recreate `refunds_order_id_active_uniq`
- **Verify:**

```sql
SELECT
  EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='refunds' AND column_name='source_key'
  ) AS source_key_col,
  EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname='public' AND indexname='refunds_source_key_active_uniq'
  ) AS source_key_idx,
  EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname='public' AND indexname='refunds_order_id_active_uniq'
  ) AS old_order_idx;
-- expect: true, true, false
```
