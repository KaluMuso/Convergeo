> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P06 — Enforce Lighthouse / perf budgets `[CODE]`

## 1. Context
**Wave 4.** Source: `01-audit-findings.md` X-6; MR-O06; `release-gates.md` G19; CLAUDE.md conv#7. **Depends on VA-P01** (tip deployed). **Live:** `perf.yml` runs Lighthouse `continue-on-error: true` (advisory); budgets not freshly probed. Locked budgets: customer routes ≤150KB gz JS, LCP ≤2.5s Fast-3G/360px, Lighthouse Perf ≥90 / SEO ≥95 / A11y ≥95. `lighthouserc.json` holds per-route ceilings.
**Type:** `[CODE]`.

## 2. Objective & scope
Make the perf budgets enforcing and re-probe the customer routes.
**Non-goals:** `ci.yml`/secret-scan (VE-P04); redesign work.

## 3. Files (edit ONLY these)
- `.github/workflows/perf.yml`
- `lighthouserc.json`
**Guardrail: sole editor of `perf.yml`/`lighthouserc.json` this wave; do not touch `ci.yml`.**

## 4. Implementation spec
- Drop the advisory `continue-on-error` on the Lighthouse/budget assertions so a regression fails the run.
- Re-probe key customer routes (home, PLP, PDP, search, categories) at 360px/Fast-3G; update ceilings to the real post-promotion baselines **only** where an intentional, justified shift occurred (document each), never to mask a regression.
- Keep the bundle-guard tolerance semantics intact.

## 10. Tests (RUN before reporting)
- `perf.yml` fails on a synthetic over-budget route; passes on the current baseline.
- Report the measured Perf/SEO/A11y + gz sizes per route.

## 11. Acceptance criteria / DoD (G19)
- [ ] Budgets enforcing (not advisory).
- [ ] Customer routes meet ≤150KB gz / LCP≤2.5s / Perf≥90 / SEO≥95 / A11y≥95, or a documented waiver per route.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P06 — Enforce Lighthouse / perf budgets
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** any ceiling change + justification · **TESTS:** paste Lighthouse/budget results · **EXCERPTS:** the enforcing-config diff · **QUESTIONS:** …
