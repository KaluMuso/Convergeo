> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (**batch 2**). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (`git worktree add /tmp/base origin/master`). **⚠ DEFERRED-AC:** the 100-concurrent-checkout run + p95<500ms measurement need deployed staging this build env lacks — build the k6 scripts + thresholds + the post-run invariant-check script + docs, validate them offline (k6 parse/`--vus 1 --iterations 1` dry-run if k6 is available; else script lint), and mark the live-load-numbers AC founder/staging-gated.

# M16-P08 — Load test (k6)

## 1. Context

**Grounded against as-built `master` (M16-P07 E2E merged):** the money-critical races are OURS to prove safe under load — **reservations, order creation, ledger postings (`post_transaction`), and invoice counters** (sequential ZRA invoice numbers). Escrow is implicit; release computes net via `compute_net_ngwee`. Money = integer ngwee. **Lenco is STUBBED for load** (no sandbox hammering). **No staging reachable here** — so the k6 scripts + thresholds + invariant-check are the deliverable; the live 100cc run is founder/staging-gated.
Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P08.

## 2. Objective & scope

k6 load scripts (`checkout-load.js` — 100 concurrent cart→reserve→order→payment-initiate against staging w/ a Lenco stub; `browse-load.js` — search+PLP read mix), run procedure + pass thresholds + tuning-log README, a **post-run invariant-check script** (zero oversells / zero ledger imbalances / zero invoice-number gaps), and a findings doc. Threshold target: **p95 <500ms at 100cc checkout; zero oversells/ledger-imbalance/invoice-gaps.**
**Non-goals:** no app code change, no migration, no real Lenco calls (stub), no CI-per-PR gate (staging-dependent). Live numbers are founder-gated.

## 3. Files (create/modify ONLY these)

- **Create:** `load/k6/checkout-load.js` (100cc cart→reserve→order→payment-initiate; env-driven `BASE_URL`; Lenco-stub flag; encoded thresholds `http_req_duration p95<500`, checks on 2xx + no-oversell response) · `load/k6/browse-load.js` (search + PLP read mix) · `load/README.md` (run procedure, pass thresholds, tuning log) · `load/invariant-check.sql` (or `.py`) (post-run: oversell check = sum(reserved) ≤ stock; ledger balance = Σ debits==Σ credits per account; invoice-number gap check = no holes in the sequence) · `docs/ops/load-test-results.md` (findings template + any local dry-run)
  **Guardrail: nothing else. Do NOT touch app source, db.ts, migrations, CI workflows, e2e/, other pebbles' files.**

## 4. Implementation spec

- **`checkout-load.js`:** k6 default fn drives cart→reserve→order→payment-initiate; `options.scenarios` ramps to **100 VUs**; `thresholds` encode `http_req_duration: ['p95<500']` + custom checks (no oversell error, order created, ledger posted). `BASE_URL`/auth from env; Lenco stubbed via a flag/base-url swap (never a real Lenco endpoint).
- **`browse-load.js`:** read-heavy search + PLP mix at a realistic ratio; latency thresholds.
- **`invariant-check` (SQL/py):** run AFTER a load run against the target DB — assert (1) no oversell (reserved ≤ available per listing), (2) ledger balanced (per-account debits==credits; escrow implicit but Σ nets consistent), (3) invoice numbers gapless. Exit non-zero on any violation. This is the money-safety proof.
- **`README.md`:** exact run commands (`k6 run`), env vars, thresholds, and a tuning log; **clearly mark the 100cc-on-staging run as founder/staging-gated.**

## 5–9. Security etc.

Lenco stubbed (no provider hammering); no committed creds (env only); the invariant-check is the money-safety gate (**zero oversells / ledger imbalance / invoice gaps** — non-zero exit on violation); thresholds encoded (not prose); live numbers founder-gated (not fabricated).

## 10. Tests (RUN before reporting)

`k6 version` / `k6 run --vus 1 --iterations 1 load/k6/checkout-load.js` against a local API if feasible (else validate JS parses: `node --check load/k6/checkout-load.js` won't work for k6 imports — instead confirm the script structure + thresholds by eslint/tsc-free syntax review + a documented dry-run plan); run `invariant-check` against a local seeded DB if available (paste result) or document the queries + a dry-run. Clearly state what ran vs. is founder-gated.

## 11. Acceptance criteria / DoD

- [ ] k6 checkout (100 VUs) + browse scripts with encoded thresholds (p95<500); invariant-check proves zero oversells / ledger-balance / no invoice gaps (non-zero exit on violation); README run procedure + tuning log.
- [ ] **Live 100cc staging run + p95 numbers marked founder/staging-gated (deferred, not fabricated);** scripts parse/structure-validated; Lenco stubbed; no committed creds.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P08 — Load test (k6)
**STATUS/FILES/DEVIATIONS** (the checkout scenario + encoded thresholds; the three invariant checks + how they'd catch an oversell/imbalance/gap; what ran locally vs founder-gated) **/TESTS** (paste k6 dry-run or structure validation + invariant-check dry-run/queries) **/EXCERPTS** the checkout-load thresholds + the invariant-check queries — nothing else **/QUESTIONS** (state the 100cc staging run is founder-gated on staging)
