# VA-P02 — Migration apply evidence (production)

**Date:** 2026-07-19 · **Executor:** Claude via Supabase MCP (`apply_migration`) · **Project:** `dpadrlxukcjbewpqympu` (Vergeo5, eu-north-1)
**Authorization:** founder ("backup done, apply the migrations"). **Backup:** confirmed taken by founder before apply (VA-P00).

> Deviation from the runbook's staging-first sequencing: with the founder's backup + go-ahead, `0051/0053–0056` were applied **directly to production** via MCP (Supabase branching needs Pro; project is Free). This brings the schema half of Wave-3 VC-P01 forward. All five are additive/reversible and CI-proven; `kyc_records=0` so no data was mutated.

## Wave 1 status rollup
| Pebble | Status | Evidence |
| ------ | ------ | -------- |
| VA-P00 backup | ✅ founder-done (pre-apply) | founder-held artifact |
| VA-P01 promote FE | ✅ auto-deploy | `deploy-promote.md` |
| VA-P02 migrations | ✅ **applied to prod (this doc)** | below |
| VA-P03 pin API image | ⛔ pending (founder GHCR/host) | — |
| VA-P04 vendor CTA | ✅ invite-only, no broken state | `cta.md` |

## Pre-flight (read-only)
`vendors.display_name` ✓ · `vendors.owner_user_id` ✓ · `set_updated_at()` ✓ · `has_role()` ✓ · `services` ✓ · `kyc_records` rowcount **0**.

## Applied (in order, each `apply_migration` → `{"success":true}`)
| # | Migration | Nature |
| - | --------- | ------ |
| 1 | `0051_custom_access_token_role_hook` | create `custom_access_token_hook` fn + grants + `auth_admin_read_user_roles` policy on `user_roles`. **Dormant** — no behavior change until registered as the Auth hook. |
| 2 | `0053_translation_overrides` | new admin-only table + RLS |
| 3 | `0054_service_reviews` | new table + verified-engagement SECURITY DEFINER trigger + RLS (FORCE) |
| 4 | `0055_service_bookable` | `services.bookable` + `booking_price_ngwee` columns + check |
| 5 | `0056_kyc_integrity` | status lifecycle CHECK (`pending→submitted` migrated **0 rows**), immutable-evidence columns, `guard_kyc_record_integrity` trigger, `kyc_orphaned_tier_report` view |

## Post-apply verification (read-only)
```
hook_0051=true · translation_overrides_0053=true · service_reviews_0054=true
services_bookable_0055=true · kyc_guard_0056=true · orphan_view_0056=true
kyc_orphaned_tier_report rows = 3   ← the 3 orphaned-tier vendors (VC-P01 target)
kyc_records rowcount = 0            ← unchanged
```
**DB drift closed (DL-3 / MR-S01 objects / MR-S11).** Live now carries `0051/0053–0056`.

## Follow-ups (not regressions)
1. **Version-key skew — DBA reconcile.** `apply_migration` recorded these under timestamp versions (`20260719134948…135053`), not the `0051`-style prefixes — same as the pre-existing `0052` (`20260717100303`). Before the next CLI migration run:
   `supabase migration repair --status applied 0051 0052 0053 0054 0055 0056`
   to align `schema_migrations` with the repo (the existing MR-S01 clean-up, now extended to these five).
2. **Two new security-advisor WARNs** — `guard_kyc_record_integrity` + `validate_service_review_verified_engagement` show as anon/authenticated-executable SECURITY DEFINER. They are **trigger** functions (Postgres blocks direct RPC calls) and are **identical to master's own posture** on a fresh CI apply (same pattern as the accepted `has_role`/`is_verified_business` WARNs). Repo-level hardening backlog, not introduced by this apply.

## Carve-outs (remain Wave-3, founder action)
- **`0051` role hook is DORMANT.** Enable in Supabase → Authentication → Hooks → Custom Access Token to activate role→JWT sync (VC-P03). ⚠️ Test first — a bad hook breaks all logins.
- **3 KYC orphans** are now *identified* by `kyc_orphaned_tier_report`; repair is the manual guarded step (VC-P01) — never auto-upgrade.
