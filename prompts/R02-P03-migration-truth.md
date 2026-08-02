> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P03 — Migration truth: production ledger vs repo `[OPS]`

## 1. Context
**Wave W1.** Depends on **R02-P01**.

Verified 2026-08-01: the staging project **`vergeo-sandbox`** carries **all 79 migrations `0001`–`0079`** in clean sequential order. **Production (`dpadrlxukcjbewpqympu`) is at ledger tip `0071`** — `0072`–`0079` (M18 intake + M17 Clips) are unapplied, so on production the Clips and intake tables do not exist and the `clips`, `clips_comments`, `waha_vendor_intake` flag rows are **absent**. Both flag readers fail closed on a missing row, so the posture is safe — but it means the M17/M18 runbooks cannot be followed on production, and RG-1 cannot clear.

Staging has already proven the `0072`→`0079` sequence applies cleanly. This is the one migration risk that has been retired by evidence rather than argument.

**Type:** `[OPS]`.

## 2. Objective & scope
Either apply `0072`–`0079` to production and record the ledger, or record a dated decision to hold — and make the status docs say which.
**Non-goals:** writing new migrations; enabling any flag.

## 3. Files (edit ONLY these)
- `docs/production-readiness/<YYYY-MM-DD>/migration-truth.md` (new)
- `docs/plan/00-status.md` — the RG-1 row only

## 4. Implementation spec
1. **Back up first.** A dated dump precedes any DDL (this is VA-P00, still open). Record location, size, checksum, timestamp. **Do not run the apply without it.**
2. Apply `0072`→`0079` **in order** — never in parallel, never renumbered.
3. Re-read the ledger and confirm the tip is `0079`.
4. Confirm the three flag rows now exist and read **`false`**: `clips`, `clips_comments`, `waha_vendor_intake`. **Do not enable any of them** — F-V4 and the M18 Stage-1 checklist gate those, not this pebble.
5. Confirm FORCE RLS on the new tables and run the Supabase security advisor; record any new lint.

**If the decision is to hold instead:** record why, and state plainly that the M17/M18 runbooks are unrunnable on production until it changes.

## 5. Security / conventions
Additive-only; no data migration. Do not touch `public_launch` or `zamtel_collections`.

## 10. Tests (RUN before reporting)
- Ledger listing before and after.
- `select flag, enabled from feature_flags where flag in ('clips','clips_comments','waha_vendor_intake')` → three rows, all `false`.
- Supabase security advisor, before and after.
- A smoke pass on the customer app: the catalogue still renders (a schema apply must not disturb a working surface).

## 11. Acceptance criteria / DoD
- [ ] Backup artifact recorded **before** any DDL.
- [ ] Production ledger tip = `0079`, or a dated hold decision is recorded.
- [ ] All three flags exist and are `false`; none enabled.
- [ ] No new security-advisor findings, or each is triaged.
- [ ] RG-1's migration clause updated to match reality.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P03 — Migration truth
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste both ledger listings + the flag query · **EXCERPTS:** backup manifest · **QUESTIONS:** …
