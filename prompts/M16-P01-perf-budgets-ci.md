> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free where possible (dev-only tooling ok in root/customer devDeps). **From this pebble onward every wave is budget-policed per-PR.**

# M16-P01 — Performance budgets in CI

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **CI exists (M01-P09, W5):** `.github/workflows/ci.yml` (8 jobs) — **do NOT edit it**; add a **new** `.github/workflows/perf.yml`. **You are the sole `.github/**` + `scripts/ci/**` editor this wave.** All customer shop routes exist (W7–W9): home, PLP (`c/[...slug]`), PDP (`p/[slug]`), search, checkout-entry.
- **Budgets (CLAUDE.md convention #7, CI-enforced):** customer routes **≤150 KB gz JS**; **LCP ≤2.5s Fast-3G/360px**; Lighthouse mobile **Perf ≥90 / SEO ≥95 / A11y ≥95**; images WebP/AVIF + srcset + lazy (no raw `<img>`, no unoptimized public images).
- **No hosted staging assumed** — run Lighthouse against a **local production build** (`next build && next start` of `apps/customer`) so the job is self-contained (no Vercel-preview dependency). `next build` already emits per-route JS sizes — the bundle guard parses those (or the `.next` output) rather than shipping a new bundler.
  Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P01. **PWA/serwist = M16-P02 (not this wave).**

## 2. Objective & scope

Per-PR performance budgets: Lighthouse CI (Fast-3G/360px, LCP/Perf/SEO/A11y thresholds on home/PLP/PDP/search/checkout-entry), a **per-route JS ≤150 KB gz guard** that **fails the PR with the named route + delta vs base**, an image lint (no raw `<img>`/unoptimized public images), and a tunable budget doc. **All current routes must pass at merge.**
**Non-goals:** no PWA (M16-P02), no app code changes to hit budgets (only the CI gate + doc), no editing `ci.yml`.

## 3. Files (create/modify ONLY these)

- **Create:** `.github/workflows/perf.yml` (Lighthouse CI + guards on PR) · `lighthouserc.json` (Fast-3G/360px profile + thresholds, config-file-tunable) · `scripts/ci/bundle-guard.mjs` (per-route gz JS ≤150 KB; fail with route + delta vs base) · `scripts/ci/image-lint.mjs` (no raw `<img>`, no unoptimized public images) · `docs/ops/performance-budgets.md` (the budgets + how to tune with a justification note)
  **Guardrail: nothing else. Do NOT touch `.github/workflows/ci.yml` (M01-P09), app source, `main.py`, schema. If a dev-dependency (e.g. `@lhci/cli`) is needed, add it to the ROOT or `apps/customer` devDependencies only — note it (pnpm-lock touch is expected for tooling).**

## 4. Implementation spec

- **`perf.yml`:** on PR — build `apps/customer` (production), serve it locally, run **Lighthouse CI** (`lighthouserc.json`, Fast-3G/360px) against home/PLP/PDP/search/checkout-entry with assertions **LCP ≤2.5s, Perf ≥90, SEO ≥95, A11y ≥95**; run `bundle-guard.mjs` + `image-lint.mjs`. **A violation fails the PR with the named route + delta.**
- **`bundle-guard.mjs`:** compute per-route **gz** first-load JS for the customer app; compare against **150 KB** (and optionally vs the base branch for the delta message); exit non-zero listing each offending route + its size/delta.
- **`image-lint.mjs`:** scan customer app source for raw `<img>` usage + unoptimized public images; fail with file:line.
- **`docs/ops/performance-budgets.md`:** the thresholds, the Fast-3G/360px profile, and **how to change a budget (requires a justification note in the config)**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

CI-only; thresholds config-file-tunable with a required justification note; no secrets; guards are static/local (no external infra).

## 10. Tests (RUN before reporting)

**Guard scripts against fixtures:** `bundle-guard.mjs` — a fixture with an over-budget route FAILS (named route + delta), an under-budget one PASSES; `image-lint.mjs` — a fixture with a raw `<img>` FAILS, a clean one PASSES. `lighthouserc.json` smoke (valid config). Confirm the **current customer routes pass** the bundle guard locally (`pnpm --filter customer build` + run the guard). `pnpm lint`, `pnpm typecheck` (root). Note: the LHCI job itself runs on CI (needs the built app) — paste the guard-script fixture results.

## 11. Acceptance criteria / DoD

- [ ] A violating PR fails with the named route + delta; all current routes green at merge (bundle guard passes locally).
- [ ] Thresholds config-file-tunable with a required justification note; image lint catches raw `<img>`/unoptimized public images.
- [ ] New `perf.yml` only (ci.yml untouched); guard scripts have pass/fail fixture tests; repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P01 — Performance budgets in CI
**STATUS/FILES/DEVIATIONS** (note any devDep added + why local-build vs staging) **/TESTS** (paste bundle-guard pass/fail fixture output + current-routes-pass + image-lint fixture) **/EXCERPTS** the bundle-guard threshold/delta logic — nothing else **/QUESTIONS**
