# Wave 2 — code-readiness rollup & who-does-what-next

**Date:** 2026-07-19 · **Base:** `master @ 619c994` + this branch · **Executor:** Claude (autonomous verifier, no creds, no prod money)

Consolidates the Wave-2 verifier sweep and states, per gate, **who** unblocks it next. The pattern throughout: I can verify the **code** (Python + DB-trigger, on a throwaway local PG16+pgvector cluster); the **live drills / OPS / creds** are the founder's; the remaining **CODE pebbles** are Cursor's (prompts already written).

## A. Code-verified by me (no creds, no production contact)

| Gate cluster | What was proven | Evidence |
| ------------ | --------------- | -------- |
| **G3 money (S1–S3 code)** | ledger zero-sum (double-enforced), settlement-before-success fail-closed, `23505` webhook dedupe, stable-key refund idempotency, no-double-pay payout, release ordering, **no float on money** — 259 fake + 60+ DB-trigger tests; all 56 migrations replay clean | `money-code-readiness.md` |
| **S5 KYC lifecycle (code)** | `0056` guard trigger (blocks client mutation + immutable decision evidence + tier-after-decision immutability), `kyc_orphaned_tier_report` (report-only), submit→under_review→approve lifecycle, tier caps/privileges — **59 tests** (`test_kyc_integrity` 12, `test_admin_kyc` 9, `test_kyc_caps`/`archetype`/`media` 38) | this doc |

`0056` is already **live in prod** (applied Wave 1, VA-P02); the orphan report returns the 3 known orphaned-tier vendors there. So S5's DB objects exist in prod and are code-proven here — the remaining S5 gap is the **live admin drill** (below), not the code.

**Verdict:** the "money & KYC are CODE_COMPLETE and correct" claims the Go/No-Go leans on are **independently upheld**.

## B. Founder-gated — needs creds / a live stack / OPS (I can't do via MCP)

| Gate / pebble | Action | Why founder |
| ------------- | ------ | ----------- |
| **S1–S3 live** (VB-P01/P02/P03) | Run MoMo + card sandbox checkouts on the isolated stack; replay a webhook | No MCP call originates a Lenco push; Supabase branching is Pro-gated. I verify the ledger via Supabase MCP **after** each run — *once the Supabase connector is re-authorized* (it dropped auth this session). |
| **S4 workflows** (VD-P01/P02/P03) | Activate escrow-release + tickets + the 8 lifecycle n8n workflows; keep abandoned-cart/funnel OFF | OPS activation with real side effects (WhatsApp sends); money workflows also gate on S1–S3 passing. Do **not** activate prematurely. |
| **S5 live drill** | Walk submit→under_review→approve in the admin app with an admin session; confirm privileges freeze without an approved record | Needs the running admin app + an authenticated admin session. |
| **VE-P01 / VE-P02** | Create Sentry projects (`convergeo-w2`) + DSNs; UptimeRobot monitors on the 4 health endpoints | My Sentry toolset is read-only (no project creation); UptimeRobot is external. |
| **VA-P03** | Pin the API image (GHCR digest) on the OCI host | Needs GHCR/host SSH. |
| **S7** | 3–5 tester UAT journeys | Human testers. |

## C. Ready for Cursor dispatch — CODE pebbles (prompts already written)

| Pebble | Owns (exclusive file) | Prompt |
| ------ | --------------------- | ------ |
| **VB-P07** false-success E2E | `e2e/specs/checkout-false-success.spec.ts` | `prompts/VB-P07-false-success-e2e.md` |
| **VD-P04** n8n backup workflow | `infra/n8n/backup.json` + registry row | (VD prompt set) |
| **VD-P05** uptime webhook HMAC auth | `/webhook/uptime-alert` shared-secret | (VD prompt set) |
| **VD-P06** money-alerting retries | error/retry on release-job/recon/sweeper (after VD-P01) | (VD prompt set) |

Per the operating model these are implementer work (Cursor, one pebble per branch), not Claude-authored app code.

## Net Wave-2 state
Money + KYC **code UPHELD**; F-1/F-2 fixed and merged into this branch (PR #332, CI green incl. the new `money-db-triggers` job). The blocker to *closing* S1–S7 is entirely **live execution** (founder creds/stack) + the four Cursor CODE pebbles — **not** code correctness.

**Single most useful next step:** re-authorize the Supabase connector, then run the S1 sandbox MoMo checkout — I verify the ledger live via MCP and we walk S1→S6 with the code already de-risked.
