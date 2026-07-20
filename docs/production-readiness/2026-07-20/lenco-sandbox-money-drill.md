# Prompt 8 — Lenco sandbox money drill

**Date:** 2026-07-20  
**Branch:** `cursor/lenco-sandbox-money-drill-da3e`  
**Master tip assessed:** `d9839db349887ab48a52c18546e05961a62498d6`  
**Programme:** S1–S6, G3–G5 (payment / escrow / reconciliation / refund / payout) against **Lenco sandbox only**.

---

## Final verdict

# **BLOCKED_EXTERNAL**

Sandbox money drills **A–G were not executed**. This is **not** a production-money approval and **not** `PASS_SANDBOX_ONLY`.

Hard-stop rules triggered:

1. **Valid Lenco sandbox credentials unavailable** to this agent environment (F9b).
2. **Deployed API and database are not confirmed at the intended migration/code tip** (API `502`; live migration tip ≠ repo money tip for `refunds.source_key`).

No production collection credentials were used. `public_launch` was not enabled. No open production checkout was enabled. No provider secrets or full sensitive payloads were committed.

---

## Hard-rule checklist

| Rule                                                             | Observed                             |
| ---------------------------------------------------------------- | ------------------------------------ |
| Do not use production collection credentials                     | **Held** — no Lenco API calls made   |
| Do not use real customer phones / PII                            | **Held** — no checkout users created |
| Do not enable `public_launch`                                    | **Held** — no flag writes            |
| Do not enable open production checkout                           | **Held**                             |
| Do not commit credentials / webhook secrets / sensitive payloads | **Held**                             |
| Stop if sandbox creds unavailable                                | **Applied** → BLOCKED_EXTERNAL       |
| Stop if API/DB tip unconfirmed                                   | **Applied** → BLOCKED_EXTERNAL       |

---

## Preflight blockers (evidence)

### B1 — Lenco sandbox credentials (F9b)

| Probe                                                                          | Result                                                                                    |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Process env names matching `LENCO_*`                                           | **None**                                                                                  |
| `services/api/.env`, `infra/.env`, `/secrets/lenco`, common local secret paths | **Missing**                                                                               |
| Cursor Cloud environment exposes `environment.json` with secrets               | **Not exposed** (personal env; no agent-visible LENCO values)                             |
| GitHub Actions secrets list                                                    | **HTTP 403** (integration cannot read secret names/values)                                |
| Contract                                                                       | `docs/ops/lenco/lenco-api-distilled.md` — sandbox REST base + sandbox token = founder F9b |

**Conclusion:** cannot create sandbox MoMo/card collections, cannot verify callbacks against Lenco sandbox, cannot safely sign webhooks.

### B2 — Deployed API / migration tip not at intended target

| Check                                                | Result                                                                                                     |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz`                | **502**                                                                                                    |
| `GET https://api.vergeo5.com/readyz`                 | **502**                                                                                                    |
| Live migration tip (Supabase `dpadrlxukcjbewpqympu`) | `0063_revoke_execute_review_reply_guards`                                                                  |
| Repo tip money migration on master                   | `0063_refunds_source_key_uniq` (and later FORCE RLS work) — **collision / unapplied `refunds.source_key`** |
| `refunds.source_key` column live                     | **false** (SQL probe)                                                                                      |
| Prior deploy truth                                   | PR #375 — NO-GO; API digest UNKNOWN; frontend SHAs behind tip                                              |

**Conclusion:** per Prompt 8, stop — drills must not run against an unconfirmed tip (especially refund `source_key` matrix F).

### B3 — Live money plane empty (context only; not a pass)

| Table / metric        | Count |
| --------------------- | ----- |
| `payments`            | 0     |
| `ledger_transactions` | 0     |
| `orders`              | 0     |
| `refunds`             | 0     |
| `payouts`             | 0     |

---

## Requirements read (before stop)

| Source                                                                               | Coverage                                           |
| ------------------------------------------------------------------------------------ | -------------------------------------------------- |
| `docs/production-readiness/2026-07-18/consolidated/release-gates.md`                 | S1–S6, G3–G5, Go/No-Go                             |
| `docs/ops/lenco/lenco-api-distilled.md`                                              | MoMo/card/webhook/refund-as-payout/recon contracts |
| `docs/production-readiness/2026-07-19/vision-audit/WAVE-2-DISPATCH.md`               | VB-P01…P06 sequence + guardrails                   |
| `docs/production-readiness/2026-07-19/vision-audit/evidence/money-code-readiness.md` | CODE_COMPLETE ≠ live sandbox                       |
| `docs/plan/00-decisions.md`                                                          | D30 hybrid; F9b sandbox creds                      |

---

## Drill sections A–G (execution status)

Unique test references / controlled users/vendors: **not created** (blocked before fixture setup).

### A. Mobile-money collection — **NOT RUN**

| Step                                         | Status  |
| -------------------------------------------- | ------- |
| 1. Create sandbox MoMo checkout              | NOT RUN |
| 2. Pending represented as pending            | NOT RUN |
| 3. Authoritative successful sandbox callback | NOT RUN |
| 4. Exactly one successful payment            | NOT RUN |
| 5. Exactly one `CHARGE_RECEIVED`             | NOT RUN |
| 6. Balanced debit/credit legs                | NOT RUN |
| 7. Escrow hold = expected integer ngwee      | NOT RUN |

Sanitised request/callback summaries: **n/a**  
Entity IDs: **n/a**  
Expected vs actual ngwee: **n/a**

### B. Card collection — **NOT RUN**

Same accounting checks as A — **NOT RUN** (sandbox public key + API token unavailable; API 502).

### C. Webhook replay — **NOT RUN**

| Step                                                 | Status  |
| ---------------------------------------------------- | ------- |
| Replay same successful webhook                       | NOT RUN |
| Concurrent replay                                    | NOT RUN |
| No second payment / accounting / settlement / ledger | NOT RUN |

### D. False-success proof — **NOT RUN**

Pending / failed / cancelled / malformed / timed-out provider results → must not show paid/completed: **NOT RUN**.

### E. Release accounting — **NOT RUN**

| Step                                                 | Status  |
| ---------------------------------------------------- | ------- |
| Eligible lifecycle → release workflow                | NOT RUN |
| `COMMISSION_CAPTURE` before/with `RELEASE_TO_VENDOR` | NOT RUN |
| Escrow remaining balance                             | NOT RUN |
| Second release → no duplicate                        | NOT RUN |

Workflow run IDs: **n/a** (release-job inactive; see Prompt 7 n8n fleet evidence).

### F. Refund matrix — **NOT RUN** (also schema-blocked)

| Case                                       | Status                           |
| ------------------------------------------ | -------------------------------- |
| Pre-release whole-order refund             | NOT RUN                          |
| Pre-release item-scoped refund             | NOT RUN                          |
| Second item refund, different `source_key` | NOT RUN — live column **absent** |
| Retry same `source_key`                    | NOT RUN — live column **absent** |
| Refund exceeding remaining escrow          | NOT RUN                          |
| Post-release refund/payout path            | NOT RUN                          |
| Cancel path                                | NOT RUN                          |
| Partial failure and resume                 | NOT RUN                          |

### G. Reconciliation mismatch — **NOT RUN**

Detect / no destructive auto-correct / alert / sanitised evidence: **NOT RUN**.

---

## Gate-by-gate verdict (evidence actually obtained)

| Gate                          | Prior                | This session                                 | Verdict                         |
| ----------------------------- | -------------------- | -------------------------------------------- | ------------------------------- |
| **S1** Sandbox MoMo → ledger  | FAIL (CODE_COMPLETE) | Blocked: no sandbox creds + API/DB tip       | **FAIL** / **BLOCKED_EXTERNAL** |
| **S2** Sandbox card → ledger  | FAIL                 | Same                                         | **FAIL** / **BLOCKED_EXTERNAL** |
| **S3** Release accounting     | FAIL (CODE_COMPLETE) | Same + release workflow inactive             | **FAIL** / **BLOCKED_EXTERNAL** |
| **S4** n8n release + tickets  | FAIL                 | Not in money drill scope; still inactive     | **FAIL** (unchanged)            |
| **S5** KYC lifecycle          | FAIL                 | Not executed (out of A–G; tip issues remain) | **FAIL** (unchanged)            |
| **S6** False-success E2E      | FAIL                 | NOT RUN                                      | **FAIL** / **BLOCKED_EXTERNAL** |
| **G3** Payment ledger / recon | FAIL                 | No sandbox ledger proof                      | **FAIL**                        |
| **G4** No false-success       | FAIL                 | No E2E/provider matrix                       | **FAIL**                        |
| **G5** Workflow reliability   | FAIL                 | Money release ticks not activated            | **FAIL**                        |

**No gate flipped to PASS.** Sandbox success was not obtained; production-money approval is explicitly **out of scope** and **not claimed**.

---

## Failures / blockers summary

1. **F9b** — Lenco sandbox `LENCO_API_TOKEN` + `LENCO_ENV=sandbox` (+ sandbox base URL / public key as needed) not available to the agent.
2. **API** — `api.vergeo5.com` returns **502**; cannot drive checkout/webhook/internal release ticks against a healthy tip.
3. **DB tip** — live `0063` = revoke hygiene; repo refund `source_key` unapplied (`refunds_source_key_present=false`) → refund matrix F unsafe/invalid on live.
4. **Isolated stack** — Wave-2 dispatch requires throwaway DB branch + pinned sandbox API; neither provisioned in this environment.

---

## Founder / ops unblock sequence (sandbox only)

1. Supply **sandbox** credentials into the isolated stack only (`LENCO_ENV=sandbox`); never paste into git.
2. Restore API `healthz`/`readyz` **200**; pin and record API image digest at intended SHA.
3. Close RC-02 migration collision; apply `refunds.source_key` (+ FORCE RLS plan) on the **isolated** money target before refund matrix.
4. Keep production `payments` / `public_launch` **off**.
5. Re-run Prompt 8 A→G; attach redacted entity IDs, ngwee tables, execution IDs; only then consider `PASS_SANDBOX_ONLY`.

---

## Screenshots

None — no UI/checkout session was opened (blocked at preflight).

---

## Explicit non-claims

- Not `PASS_SANDBOX_ONLY`
- Not production-money GO
- Not STAGING_VERIFIED for S1–S6 / G3–G4
- Code-complete unit/DB-trigger readiness (`money-code-readiness.md`) remains separate from this live sandbox programme
