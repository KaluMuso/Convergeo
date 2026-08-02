> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P02 — Public-surface evidence: catalogue, stock, cart, search, CORS `[OPS]`

## 1. Context
**Wave W1.** Depends on **R02-P01** (a seeded, reachable staging plane).

Five readiness rows are `UNKNOWN` purely because no session has had HTTPS egress to the live hosts: API health/digest (VA-P03), vendor CTA (VA-P04), search health (VF-P04), Sentry (VE-P01), uptime (VE-P02). `UNKNOWN` is not a failure — it is an absence of evidence, and it blocks every gate that depends on it.

`scripts/ops/verify_live.sh` already implements the G0–G9 probe matrix. This pebble **runs** it and commits the result; it does not rewrite it.

**Type:** `[OPS]` — an agent prepares the runner and the evidence template, the founder executes from a host with egress and pastes redacted output.

## 2. Objective & scope
Produce a dated, committed evidence pack that answers: is the catalogue real, is stock honest, does cart/search work, is CORS correct, and what is the API actually running?
**Non-goals:** fixing what the probes find (each finding becomes its own pebble); money drills.

## 3. Files (edit ONLY these)
- `docs/production-readiness/<YYYY-MM-DD>/public-surface-evidence.md` (new)
- `scripts/ops/verify_live.sh` — **only** if a probe is missing or broken

## 4. Implementation spec
Record, for the staging target first and production second:

| Probe | Record |
| --- | --- |
| `GET /healthz`, `/readyz`, `/fingerprint` | status, `env`, **`git_sha`**, `supabase_project_ref` |
| `GET /catalog/listings` | count, and whether any `demo/%` public id appears (must be **zero**) |
| Listing stock | `stock_mode`/`stock_qty` honesty vs what the PDP renders |
| Cart | add → merge → price re-derivation, as guest and as consumer |
| `GET /search?q=…` | `total`, and **`degraded`** (VF-P04's open question) |
| CORS | `Origin:` from each app origin → allowed; a foreign origin → refused; `*` never present with credentials |
| Frontend health | `/en/health` on customer, vendor, admin (admin should be Access-gated) |
| Migration truth | ledger tip of **both** Supabase projects |

**If `git_sha` reports `unknown`, say so and stop treating the deploy as traceable** — that is a finding, not a formatting problem.

## 5. Security / conventions
Redact tokens, ids and PII from every pasted response. Secret **names** only. Read-only: no writes, no flag flips, no deploys.

## 10. Tests (RUN before reporting)
- `bash scripts/ops/verify_live.sh` against staging, then production; paste both matrices.
- Any probe that cannot run → record `UNKNOWN` **with the reason**. Never infer a pass.

## 11. Acceptance criteria / DoD
- [ ] Every row is `PASS`, `FAIL` or `UNKNOWN` **with evidence or a stated reason** — no blanks.
- [ ] The five previously-`UNKNOWN` rows are now answered, or the reason they still cannot be is recorded.
- [ ] Zero demo listings on any public surface.
- [ ] The pack is dated and linked from `docs/plan/00-status.md`.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P02 — Public-surface evidence
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste both probe matrices · **EXCERPTS:** the fingerprint block · **QUESTIONS:** …
