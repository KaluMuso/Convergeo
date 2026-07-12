> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (**batch 2, dispatched LAST** — depends on P01–P08; the launch checklist enumerates every other pebble's status). **Touch ONLY your files below.** **Your migration is `0030` (0029 is the latest on master).** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (`git worktree add /tmp/base origin/master`). **⚙ CI GATING:** your DB tests must be isolation-clean; converger wires them into the rls step + **hand-authors the `db.ts` block for `beta_invites` — do NOT edit `packages/types/src/db.ts`; paste your CREATE TABLE in the report.** **Run the FULL `uv run pytest` before reporting.** **⚠ DEFERRED-AC:** the go/no-go SIGN-OFF depends on founder gates F1/F2 (domain/PACRA), F4 (counsel), F9 (Lenco) — build the checklist with every gate + evidence-link slot; leave founder-gated lines UNCHECKED with a clear owner, do NOT fake sign-off.

# M16-P09 — Beta tooling & go/no-go

## 1. Context

**Grounded against as-built `master`:** all mountains M01–M16 built through Wave 18 batch 1 (this is the final pebble). Feature-flag pattern + config table exist; RLS+FORCE on every table; auth is phone-OTP/email/Google; outbox pattern for notifications; admin app separate origin. **Migration `0030` is the next free number.** Router auto-discovery: a new `app/routers/beta.py` exposing `router` is auto-mounted (no `main.py` edit).
Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P09.

## 2. Objective & scope

Beta invite tooling (invite codes + capacity + a flag-controlled gate middleware: invite-only → public via flag flip, no deploy), an invite-gate UI, a feedback widget (floating, optional screenshot → admin/outbox), and `docs/plan/launch-checklist.md` (go/no-go: every M-success-criterion, founder gates F1–F9 status, budgets, E2E, restore drill, counsel F4, sign-off lines).
**Non-goals:** no change to other pebbles' code, no real founder sign-off (gates are founder actions — enumerate + link, don't fake), no new payment logic.

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0030_beta_invites.sql` (invite codes: code, capacity, used_count, expires_at, active flag; RLS+FORCE — admin write, invite-code redemption via a `SECURITY DEFINER` function or service-role; no client table write) · `services/api/app/routers/beta.py` (create/list invites [admin]; redeem-code [gated]; the gate-check helper — flag-controlled: when the `public_launch` flag is on, the gate is a no-op) · `apps/customer/app/[locale]/(marketing)/beta/page.tsx` (invite-code entry gate UI) · `packages/ui/src/feedback-widget.tsx` (floating widget; optional screenshot; submit → admin/outbox) · `docs/plan/launch-checklist.md` (the go/no-go checklist) · `services/api/tests/test_beta.py`
- **Modify (ONLY your own new route entries):** `services/api/app/core/ratelimit_policies.py` — add a policy entry for EACH of your new mutating routes (`POST /beta/invites`, `POST /beta/redeem`, and any other mutating beta route) so the M15-P04 startup assert `assert_all_mutating_routes_covered` passes and the app constructs. This is the M15-P04 contract ("a route that lacks a limit → add the registry entry"), NOT a refactor — add only your rows, touch nothing else in that file.
  **Guardrail: nothing else. Do NOT edit `packages/types/src/db.ts` (converger hand-authors the `beta_invites` block — paste your DDL), `main.py`, other routers, other pebbles' files, other migrations, or any `ratelimit_policies.py` entry that isn't your own new route.**

## 4. Implementation spec

- **`0030_beta_invites.sql`:** `beta_invites(id, code unique, capacity int, used_count int default 0, expires_at, active bool, created_at)`; RLS+FORCE — admin (has_role) read/write; redemption path via a `SECURITY DEFINER` function that atomically checks `active AND used_count < capacity AND now()<expires_at` then increments (no race → no over-capacity); NO client insert/update/delete grant. Additive + reversible.
- **`beta.py`** (auth, admin-scoped for create/list; rate-limited redeem): `POST /beta/invites` (admin), `GET /beta/invites` (admin), `POST /beta/redeem` (gated — valid/invalid/exhausted/expired codes → distinct outcomes, idempotent). **Gate helper reads the `public_launch` feature flag** — flag ON ⇒ gate is a no-op (public); flag OFF ⇒ invite required. **Add a `ratelimit_policies.py` entry for each new mutating route** (per §3 — your own rows only) so the M15-P04 startup assert passes and the app constructs; use the existing rate-limit dependency on the routes themselves.
- **UI:** `beta/page.tsx` invite-code entry (360px, i18n, submit → `/beta/redeem`); `feedback-widget.tsx` floating dismissible widget, optional screenshot (canvas), submit → admin inbox/outbox; i18n via existing namespaces (do NOT create `marketing.json` — it exists; append minimally if unavoidable).
- **`launch-checklist.md`:** enumerate EVERY launch gate — each M-mountain success criterion (with an evidence link to the pebble/test/PR), founder gates **F1–F9** (status + owner), budget-green (bundle/Lighthouse), E2E-green (M16-P07, staging-gated), restore-drill-done (M15-P09, staging-gated), load-test-passed (M16-P08, staging-gated), counsel **F4**, and explicit **sign-off lines**. Founder/staging-gated items stay UNCHECKED with a clear owner — do NOT fake completion.

## 5–9. Security etc.

Beta gate = feature flag (no deploy to flip); redemption atomic + capacity-safe (no over-capacity race — assert concurrent-redeem in a test); admin-scoped invite management (RLS proven); `SECURITY DEFINER` redemption function is the only client path to decrement capacity; feedback widget sanitizes input (no injection into the outbox email); migration additive + RLS+FORCE (no client table write); no fake sign-off (founder gates enumerated, not checked).

## 10. Tests (RUN before reporting)

`test_beta.py`: gate middleware (valid → allowed; invalid/expired/exhausted → rejected distinctly); **capacity race** (concurrent redeems never exceed capacity); flag behavior (flag ON ⇒ gate no-op/public; OFF ⇒ invite required); admin-only invite create (non-admin denied); feedback submission round-trips to the outbox. `pnpm --filter customer build/typecheck/lint`; migration replays clean; **full `uv run pytest`** (confirm the M15-P04 rate-limit startup assert still passes with your new routes — if not, note the policy entries the converger must add).

## 11. Acceptance criteria / DoD

- [ ] Cohort invitable/gated (capacity-safe, atomic); flag-flip opens public (no deploy); checklist enumerates every launch gate with evidence links; feedback round-trips; migration `0030` additive + RLS+FORCE.
- [ ] **Founder-gated lines (F1/F2/F4/F9, staging E2E/drill/load) left UNCHECKED with owners (not faked);** `db.ts` DDL pasted for converger (not edited); customer build + full API suite + migration replay green; startup-assert status noted.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P09 — Beta tooling & go/no-go
**STATUS/FILES/DEVIATIONS** (the gate flag mechanism; the atomic capacity-safe redemption; the checklist structure; **the `0030` beta_invites DDL verbatim for the converger's db.ts**; whether your new mutating routes need `ratelimit_policies.py` entries from the converger) **/TESTS** (paste gate + capacity-race + flag + admin-only + full-pytest tail + migration replay) **/EXCERPTS** the SECURITY DEFINER redemption function + the gate-flag helper + the checklist's founder-gate section — nothing else **/QUESTIONS** (list exactly which founder gates block sign-off + which routes need converger rate-limit-policy entries)
