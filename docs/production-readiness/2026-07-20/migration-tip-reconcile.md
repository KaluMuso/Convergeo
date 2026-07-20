# RC-02 migration tip reconcile — 2026-07-20

## Before

- Live Supabase `dpadrlxukcjbewpqympu` tip is `0063_revoke_execute_review_reply_guards` (`20260720074318`) and is already applied.
- Repo `origin/master` used the `0063` prefix for `refunds.source_key`; that SQL is not on live and `refunds.source_key` is absent.
- Repo `0064_force_rls_launch_tables.sql` is not applied live; `product_relations`, `ticket_type_instances`, and `ticket_type_price_tiers` still have `FORCE` RLS false.

## After RC-02

- Repo `0063_revoke_execute_review_reply_guards.sql` matches the already-applied live migration.
- Repo keeps `0064_force_rls_launch_tables.sql` as-is.
- Repo renumbers the unchanged source-key body to `0065_refunds_source_key_uniq.sql`.

## Apply order after review

1. Already live: `0063_revoke_execute_review_reply_guards`.
2. Apply `0064_force_rls_launch_tables.sql`.
3. Apply `0065_refunds_source_key_uniq.sql`.

Do not apply these migrations from this agent; parent review will handle Supabase MCP application after merge.

---

## Live apply (2026-07-20T15:56Z — same session)

Precheck: `orders=payments=refunds=0`. Applied via Supabase MCP on `dpadrlxukcjbewpqympu`:

| Migration                      | Ledger version   | Verify                                                                                                |
| ------------------------------ | ---------------- | ----------------------------------------------------------------------------------------------------- |
| `0064_force_rls_launch_tables` | `20260720155653` | `relforcerowsecurity=true` on `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations` |
| `0065_refunds_source_key_uniq` | `20260720155702` | `refunds.source_key` **exists**; tip = `0065_refunds_source_key_uniq`                                 |

Repo reconcile landed as PR **#387**.
