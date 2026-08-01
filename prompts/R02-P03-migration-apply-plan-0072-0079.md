> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P03 — Production apply plan for `0072`→`0079` `[OPS]`

## 1. Context

**Wave R2-A.** Source: `docs/plan/r02/01-strategy-convergence.md` §2.5 (RG-1), §5; release gate
**RG-1**; operational step **O1**.

RG-1 is the hard blocker. Verified read-only on **2026-08-01**:

| Project                                     | Ledger tip                       | Note                                    |
| ------------------------------------------- | -------------------------------- | --------------------------------------- |
| `dpadrlxukcjbewpqympu` (**production**)     | `0071_vendor_listing_compare_at` | `0072`–`0079` **unapplied**             |
| `iyasmrmbcrvlfxpzescb` (**vergeo-sandbox**) | `0079_clip_cost_guard`           | the **full set**, clean sequential keys |

The sandbox project (created 2026-07-28) already holds exactly the set production is missing, under
clean `0051`–`0079` keys, with all five feature flags present and **`false`** and every money table at
zero. **The apply has therefore already succeeded once on a real Supabase project** — that is the
rehearsal, and this pebble's job is to turn it into a plan an operator can execute on production
without improvising.

**Two facts the plan must confront.**

1. **The two ledgers are not shaped alike.** Production stores `0052` as
   `version=20260717100303, name=0052_product_relations`, and several rows are numerically out of
   order (`0052` before `0051`, `0070` before `0069`). The sandbox stores clean `0051`…`0079`. A
   rehearsal on one is not automatically a rehearsal on the other, and `max(version)` on production
   returns a timestamp, not `0071`.
2. **None of `0072`–`0079` carries a down/rollback note.** Convention #6 requires every migration to
   be "reversible or documented why not". Files up to `0059` mostly carry a `-- Down (manual):`
   header; `0060`, `0064`, `0066`–`0068`, `0070`–`0071` and **all eight of `0072`–`0079`** do not.
   The operator must not be asked to improvise a rollback at the moment one is needed.

Dependency order is already verified file-by-file in
`docs/production-readiness/2026-07-27/release-truth.md` §1.1 — reuse it, **re-verify it**, do not
re-derive it from scratch.

**Type:** `[OPS]` — plan, verification SQL and runbook. **Cursor writes; the founder/operator
applies.** This pebble applies nothing.

## 2. Objective & scope

Produce everything an operator needs to apply `0072`→`0079` to production, confirm it worked, and know
what to do if it did not.

**Non-goals — do NOT do these:**

- **Do not apply any migration**, to any project, including the sandbox. Not with `supabase db push`,
  not with `psql`, not via MCP.
- **Do not edit any file under `supabase/migrations/`.** All eight are merged and, on the sandbox,
  already applied — editing one now would desynchronise the two ledgers. If a migration genuinely
  needs a fix, **stop and report it**; do not fix it here.
- **Do not renumber anything.**
- **Do not flip a flag, seed, deploy, activate a workflow, install WAHA or run a payment.** Applying
  `0072`/`0077` creates flag rows that ship **`false`**; the plan must state that enabling them is a
  separate, founder-gated act (RG-2 / RG-3).
- **Do not edit `scripts/ops/verify_live.sh`** — R02-P02 is its sole editor this wave. Specify what
  you need from it; do not write it.
- Do not add application code, a frontend change, or a dependency.

## 3. Files (create/modify ONLY these)

- `docs/plan/r02/02-migration-apply-plan.md` **(new)** — the operator-facing plan.
- `scripts/db/verify-0072-0079.sql` **(new)** — idempotent, **read-only** object/flag verification.
  Follow the existing convention in `scripts/db/` (see `ledger-invariants.sql`).
- `docs/ops/supabase-workflow.md` — add a short pointer from §"Push to staging / production" to the
  plan. **Pointer only** — do not restructure the document.

**Guardrail: modify ONLY these three files.** In particular: nothing under `supabase/migrations/`,
and not `scripts/ops/verify_live.sh`.

## 4. Implementation spec

### 4.1 The plan document

Write for an operator working alone, possibly at night, possibly after something has gone wrong.
Every step names its command, its expected output, and what to do when the output differs.

1. **Pre-flight.**
   - A fresh backup exists — timestamp and checksum recorded **before** anything is applied. The plan
     must refuse to proceed without one.
   - Record the pre-apply ledger state verbatim (`version` **and** `name` for every row) so the
     before/after diff is evidence, not memory.
   - Confirm the target project ref is production and not the sandbox. State both refs explicitly in
     the plan so a copy-paste error is visible.
   - Confirm `public_launch=false` and `zamtel_collections=false` before and after. This apply must
     not change either.

2. **Apply order** — `0072 → 0073 → 0074 → 0075 → 0076 → 0077 → 0078 → 0079`, strictly sequential.
   Reproduce the dependency table (which object each file creates, and what it depends on) and
   **re-verify it by reading the eight files**, citing what you checked. State plainly that no file
   references an object created by a later-numbered file.

3. **Ledger-key reconciliation.** Explain the mixed-key situation in production, and state what the
   ledger should look like afterwards. Warn that `max(version)` is not a usable tip on this project
   and that the operator should compare the **set** of numeric prefixes, not a single string. Note
   that R02-P02 is landing exactly that reporting fix in `verify_live.sh`, and that the plan's SQL is
   the independent cross-check.

4. **Post-apply assertions** — every one a command with an expected result:
   - all eight prefixes `0072`…`0079` present in `schema_migrations`;
   - the M18 tables exist (`intake_sessions`, `intake_deep_links`, …) and the M17 tables exist
     (`video_clips`, `clip_comments`, `clip_views`, `clip_spend_monthly`, `clip_weekly_caps`, …);
   - the three flag rows **exist and read `false`**: `waha_vendor_intake`, `clips`, `clips_comments`.
     Call out the distinction the release-truth pack drew — before the apply the checklist line is
     "confirm the row is false" and it _cannot be ticked_ because the row does not exist; after the
     apply it becomes "confirm the row exists and is false";
   - `payments` / `orders` / `ledger_transactions` / `kyc_records` still `0`;
   - FORCE RLS holds on the new tables; the RLS matrix and security advisor stay green.

5. **Rollback position per migration.** The files carry no down-notes, so supply one for each: state
   whether it is cleanly reversible (config-row inserts like `0072`/`0077`/`0078` are), what the
   reverse statement is, and where reversal is **not** clean (table drops with data, storage policies
   in `0074`). Where the honest answer is "roll forward, do not reverse", say that and say why —
   convention #6 accepts a documented reason but not silence.
   - Be explicit that reversal is a **last resort** and that restoring the pre-apply backup is the
     primary recovery path (`infra/ROLLBACK.md`, RTO ≤30 min / RPO ≤24 h).

6. **What this apply does and does not turn on.** One short, unmissable section: applying these eight
   migrations creates schema and **three flags that are all `false`**. It starts no WAHA lane, publishes
   no clip, spends no Cloudinary credit and moves no money. RG-2 and RG-3 remain NOT*RUN afterwards
   and become \_runnable*, not passed.

### 4.2 The verification SQL

- Strictly **read-only** and **idempotent** — safe to run before, after, and twice.
- Returns a boolean/label result table an operator can read at a glance: one row per assertion with a
  clear name and a PASS/FAIL column. Do not make the reader diff two opaque outputs by eye.
- Covers: the eight ledger prefixes; each expected table via `to_regclass`; each of the three flags
  (present **and** `false` — distinguish "absent" from "present and true" in the output, because they
  demand different responses); the money-table zero check.
- Must behave sensibly when run **before** the apply — reporting the pre-state, not erroring — so the
  same file produces the before and after evidence.
- No DDL, no `SET`, no writes of any kind.

## 9. Security

- **Nothing is applied by this pebble.** The SQL is `SELECT`-only.
- No DSN, service-role key or project credential in any committed file — names only, values from the
  operator's environment (standing convention; see `scripts/ops/launch_gates.sh` header).
- The plan must instruct the operator never to disable RLS to make an apply succeed. If a migration
  fails because of RLS, that is a finding to report, not an obstacle to remove.
- Feature flags stay `false`. The plan may not contain a command that enables one.

## 10. Tests / verification (RUN before reporting)

- `scripts/db/verify-0072-0079.sql` executes cleanly against a **local** stack at repo tip
  (`supabase db reset`) — paste the full result table.
- Run it again against a local stack **stopped at `0071`** (pre-apply shape) and paste that result
  table too — it must report the pre-state rather than erroring. This is the run that proves it is
  usable as pre-flight evidence.
- Re-run once more on the same database to prove idempotence: byte-identical output.
- `bash scripts/ci/migration-replay.sh` green at repo tip (the duplicate-prefix guard plus a clean
  ordered replay is the independent check that the apply order is sound).
- Confirm `git diff --exit-code -- supabase/migrations/` is clean.
- Confirm `git diff --exit-code -- scripts/ops/verify_live.sh` is clean.

## 11. Acceptance criteria / DoD

- [ ] Plan states both project refs explicitly and cannot be followed against the wrong one by accident.
- [ ] Backup-first is a hard pre-flight step, with the pre-apply ledger captured verbatim.
- [ ] Apply order `0072`→`0079` reproduced **and independently re-verified** against the eight files,
      with the check described.
- [ ] Mixed ledger-key situation explained, with the "compare the set, not `max(version)`" warning.
- [ ] Post-apply assertions are commands with expected outputs, including the three flags existing and
      reading **`false`**, and the money tables still `0`.
- [ ] A rollback position is documented for **each** of the eight migrations, with "roll forward, do
      not reverse" stated and justified where that is the honest answer.
- [ ] An unmissable section stating this apply turns nothing on, and that RG-2/RG-3 stay NOT_RUN.
- [ ] `verify-0072-0079.sql` is read-only, idempotent, runs meaningfully **before and after**, and
      distinguishes flag-absent from flag-true.
- [ ] **No migration applied anywhere**; no file under `supabase/migrations/` modified;
      `scripts/ops/verify_live.sh` untouched.
- [ ] No flag flipped, nothing seeded, deployed or activated.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P03 — Production apply plan for `0072`→`0079`
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the verification SQL result table from **all three** runs (repo tip, pre-apply shape,
idempotence re-run) plus the `migration-replay.sh` result
**EXCERPTS:** the dependency re-verification (what you read in each of the eight files and what it
depends on), and the flag-state assertion SQL
**ROLLBACK:** one line per migration — cleanly reversible, or roll-forward-only with the reason
**APPLIED:** confirm explicitly that **nothing was applied to any project**, sandbox included
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
