# Wave 3 — Dispatch Runbook (VM-C · Trust, KYC, Security & RBAC)

**Date:** 2026-07-19 · **Gate on entry:** Wave 1 (migrations proven on the staging branch) + Wave 2 (money proof) + decisions **D31–D34 locked** ✓ · **Prompts:** `prompts/VC-P01…P09`.
This is where the **production** schema changes land — carefully, after the Wave-1 staging drill — plus the CODE hygiene/security pebbles the decisions unblocked.

## Guardrails (do NOT)
- **Backup before any PROD apply** (VA-P00 must exist; take a fresh one if stale). Apply `0056` to prod **only after** the Wave-1 staging drill (VA-P02) passed.
- **KYC orphan repair is MANUAL and guarded** — never `UPDATE vendors SET kyc_tier`, never auto-create `kyc_records`, never auto-upgrade (D-FD-12/NB-14).
- **No invented admin roles** — D33 locks single `admin`; VC-P07 is a docs runbook, not a CRUD build.
- FORCE-RLS change must keep the security advisor + RLS matrix green (no service-role regression). No `public_launch` flip; money stays off.

## Access needed
| System | For |
| ------ | --- |
| Supabase dashboard/DB (**prod**) + backup | VC-P01 (`0056` apply + orphan repair), VC-P03 (Auth hook), VC-P09 (leaked-pw) |
| Cursor agents | VC-P02/P04/P05/P06 (CODE) + VC-P07 (DOC) |
| Zambian legal counsel | VC-P08 (DPA/NPS-Act escrow posture) |

## Execution order (3 tracks)
```
Track A  PROD DB (OPS, gated on Wave 1): VC-P01 apply 0056 + orphan repair  ‖  VC-P03 enable role hook (0051)
Track B  CODE (dispatch to Cursor, parallel-safe — disjoint files):
         VC-P02 FORCE-RLS migration ──▶ VC-P04 RLS-test registry (adds the FORCE assertions)
         VC-P05 refund-mount hygiene ‖ VC-P06 demo-exclusion ‖ VC-P07 admin-RBAC doc
Track C  OPS/legal: VC-P08 legal artifact ‖ VC-P09 leaked-password toggle
```

---

## TRACK A — Production DB rollout `[OPS]` (only after Wave-1 staging PASS + backup)
| Pebble | Do | Verify | Evidence |
| ------ | -- | ------ | -------- |
| VC-P01 | Apply `0056` to **prod** (order: API understands statuses → migrate → clients); run `/admin/kyc/orphaned-tiers`; **manually** repair the 3 orphans (proper submission→guarded approve, or clear tier via guarded path) | `0056` in prod `schema_migrations`; `guard_kyc_record_integrity` present; orphan count → 0 (or each ticketed); a bare-tier vendor **cannot** unlock wholesale/events/verified | `evidence/kyc-0056-rollout.md` |
| VC-P03 | Enable the Supabase Auth **custom-access-token hook** (`0051` applied in Wave 1) | JWT `roles` == `user_roles` for customer/vendor/admin testers; `uv run pytest services/api/tests/rls services/api/tests/test_authz_matrix.py -q` green | `evidence/role-hook.md` |

## TRACK B — CODE pebbles `[CODE/DOC → dispatch to Cursor]` (disjoint files, parallel-safe)
| Pebble | Owns | Do | Verify |
| ------ | ---- | -- | ------ |
| VC-P02 | `supabase/migrations/00NN_force_rls_ticket_tiers.sql` (**number above master's max prefix, land promptly**) | additive migration: FORCE RLS on `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations`; fix table-owner assumptions | `supabase db reset` + `scripts/ci/migration-replay.sh` green; `get_advisors(security)` shows FORCE true; no service-role/inventory regression |
| VC-P04 | `services/api/tests/rls/test_matrix.py`, `…/test_no_untested_tables.py` (**sole editor**) | add `event_categories`, `product_relations`, `service_reviews` to `EXPECTATIONS`; add FORCE assertions after VC-P02 lands | `uv run pytest services/api/tests/rls -q` green; zero untested live tables |
| VC-P05 | `services/api/app/routers/refunds.py` | remove the direct `/refunds/execute` mount; keep only `/admin/refunds/execute` under `AdminAuditedRoute` | `uv run pytest services/api/tests/test_refund_execute.py test_authz_matrix.py -q` green |
| VC-P06 | `services/api/app/routers/search.py`, `catalog.py` + seed-label script | exclude `demo/%` from public search/catalog/comparison/directory/suggest/Ask (mirror `drop_wholesale_listing_hits`); demo labelled only on demo route | new test proves public exclusion; `uv run pytest services/api/tests/test_search*.py test_catalog*.py -q` green |
| VC-P07 | `docs/ops/admin-access.md` | **(DOC, per D33)** document guarded single-`admin` grant/revoke + Cloudflare Access; **no** superadmin/moderator, no CRUD UI | runbook is copy-pasteable; authz model matches the DB CHECK |

**VC-P02 → VC-P04 note:** VC-P02 owns only the migration; VC-P04 is the sole editor of the RLS tests and lands the FORCE assertions — sequence VC-P04 after VC-P02 merges.

## TRACK C — Ops / legal `[OPS]`
| Pebble | Do | Verify | Evidence |
| ------ | -- | ------ | -------- |
| VC-P08 | Engage Zambian counsel; obtain written DPA + NPS-Act-2026 escrow posture (Lenco-held funds) | artifact reference recorded; `release-gates.md` `legal_signoff` filled (never a self-waiver) | `evidence/legal-signoff.md` |
| VC-P09 | Enable leaked-password protection in Supabase Auth | `get_advisors(security)` no longer flags `auth_leaked_password_protection`; a breached password is rejected | `evidence/auth-hardening.md` |

---

## Report back (Phase-4 review)
Paste each pebble's **IMPLEMENTATION REPORT**. Heightened scrutiny on: the `0056` prod apply order + orphan-repair evidence (no auto-upgrade), the FORCE-RLS advisor result, and role-isolation suite output. I'll map **G0 (authz/RLS/role), G11 (demo), G12 (KYC), G13 (legal), G15 (RBAC)** in `release-gates.md`, update `docs/plan/00-status.md`, and — once Wave 2 money + Wave 3 trust are both proven — assemble the **Go/No-Go pack (VE-P09, Wave 4)**.

**Wave 3 exit:** `0056` live + KYC orphans repaired (privileges require an approved record), FORCE RLS enabled (advisor green), role hook enabled (isolation suites green), demo excluded from public discovery, admin-RBAC documented, leaked-password on, legal posture written. **Real money still gated** on Wave 4 ops hardening + VE-P09 Go/No-Go — `public_launch=false` until then.
