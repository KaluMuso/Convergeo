# STG-LEDGER-02 execution report — 2026-08-16

**Operator:** Cursor Cloud Agent (STG-LEDGER-02)  
**Repository SHA certified:** `9a08540d2e0e4ad3f04bd5e2b1cb4a7d51df112c`  
**Target:** Supabase staging `iyasmrmbcrvlfxpzescb` only  
**Production touched:** **NO** (`dpadrlxukcjbewpqympu` not queried or mutated)

## Phase summary

| Phase                     | Result                                               | Evidence                                                                   |
| ------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------- |
| 1 Preflight               | PASS                                                 | `before-ledger.txt`, `before-physical-state.json`, `before-preflight.json` |
| 2 Ledger normalization    | PASS                                                 | 103 → 100 rows; 7 rehearsal rows reverted; 4 canonical aliases marked      |
| 3 Pre-push proof          | PASS                                                 | `post-repair-preflight.json` — `schema_apply_required=true`, 8 pending     |
| 4 Canonical schema apply  | PASS                                                 | 8 migrations applied; tip `20260815230000`                                 |
| 5 Post-push verification  | PASS                                                 | `final-ledger.txt`, `final-preflight.json`, reconcile OK (108 rows)        |
| 6 Documentation           | PASS                                                 | This report + readiness doc updates                                        |
| 7 Integrated staging cert | See workflow runs linked after `staging` branch push |

## Ledger transition

| Milestone              | Row count | Tip                                |
| ---------------------- | --------- | ---------------------------------- |
| Pre-repair (live)      | 103       | `20260813073039` (rehearsal alias) |
| Post-repair (pre-push) | 100       | `20260813063754`                   |
| Post-canonical push    | 108       | `20260815230000`                   |

## Eight canonical migrations applied (not six)

1. `20260812090000` — product strategy integrity
2. `20260813064106` — product strategy core contract
3. `20260813150000` — `approve_kyc_vendor` atomic
4. `20260813160000` — rate counter scope manifest
5. `20260813160100` — listing view surface telemetry
6. `20260813160200` — security definer hardening
7. `20260815194500` — privileged function EXECUTE hardening (SEC-DB-01)
8. `20260815230000` — refund provider-authoritative active index

## Post-push verification highlights

- `approve_kyc_vendor(...)` present
- `record_listing_view` 6-arg signature includes `p_surface DEFAULT 'unknown'`
- `refunds_source_key_active_uniq` partial index includes `awaiting_payout`
- Event money tables present with FORCE RLS
- `public_launch` remains **false**
- `schema_convergence.py --staging-preflight`: `schema_apply_required=false`, zero drift

## Note on apply path

Schema DDL was applied via Supabase MCP `execute_sql` with canonical ledger inserts after an erroneous MCP `apply_migration` timestamp version was corrected for `20260812090000`. Final ledger reconciles exactly with repository filenames (`reconcile_staging_migrations.py` PASS).
