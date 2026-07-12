> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (parallel batch 1). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-18 editor of `.github/workflows/perf.yml`.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (`git worktree add /tmp/base origin/master` to compare). **Run the i18n sweep + `pnpm --filter customer build/typecheck/lint` before reporting.**

# M16-P03 — i18n completeness & formatting audit

## 1. Context

**Grounded against as-built `master`:**

- **A hardcoded-string eslint rule already exists** (`packages/config/eslint-rules/no-hardcoded-strings.js`, wired as a WARN job in `ci.yml`). **Build ON it** — add a stricter repo-wide sweep script that covers template literals / `aria-*` / `<meta>` / `title` text, plus **missing-key detection (used-vs-defined diff)** and a **pseudo-locale build**.
- **`.github/workflows/perf.yml` exists** (the "Bundle, image lint & Lighthouse" workflow — M16-P01, merged W10). **You are its sole Wave-18 editor** — wire the i18n completeness gate here (same mountain, per spec). Do NOT touch `ci.yml` (its existing i18n-lint WARN job stays).
- next-intl + ICU; `formatK()` is the money formatter; ZMW/date via locale-aware helpers in `packages/i18n`.
  Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P03.

## 2. Objective & scope

Repo-wide i18n completeness: a hardcoded-string sweep (template/aria/meta coverage), missing-key detection (used vs defined), a bracketed pseudo-locale (`en-XA`) build, a `formatK`-bypass grep (raw `toLocaleString`/`Intl.`/`"K"`-prefix outside `packages/i18n`), CI wiring in `perf.yml`, and an audit-fixes doc. Fix any real violations the sweep finds (or document why deferred).
**Non-goals:** no new UI feature, no ci.yml edit (perf.yml only), no translation of content into bem/nya/fr (EN-first; pseudo-locale is the coverage proof, not real translation).

## 3. Files (create/modify ONLY these)

- **Create:** `scripts/ci/i18n-lint.mjs` (the sweep: hardcoded strings incl. template/aria/meta; used-vs-defined missing-key diff; formatK-bypass grep — exit non-zero on a real violation) · `packages/i18n/pseudo.ts` (`en-XA` bracketed pseudo-locale generator) · `docs/plan/i18n-audit.md` (findings + fixes)
- **Modify:** `.github/workflows/perf.yml` (add a blocking i18n-completeness step running `scripts/ci/i18n-lint.mjs`) · **any files with REAL hardcoded-string / formatK-bypass violations the sweep finds** (fix them via the correct i18n key — keep each fix minimal; if a fix would touch a file another Wave-18 pebble owns, DEFER it and list it in `i18n-audit.md` instead)
  **Guardrail: nothing else structural. Do NOT touch `ci.yml`, db.ts, migrations, `next.config.ts` files, or any Wave-18 sibling's owned files (PWA sw/manifest, Sentry configs, beta UI, e2e/, load/).**

## 4. Implementation spec

- **`i18n-lint.mjs`:** (1) hardcoded-string scan over `apps/**/app/**/*.{tsx,jsx}` extending the eslint rule's coverage to template literals, `aria-label`/`aria-*`, `<meta>`/`title`/`alt` text; (2) **missing-key detection** — collect `t('…')`/`getTranslations` key usages, diff against the `packages/i18n/messages/en/*.json` defined keys, fail on used-but-undefined (and report defined-but-unused as a warning); (3) **formatK-bypass grep** — flag raw `toLocaleString`/`Intl.NumberFormat`/`Intl.DateTimeFormat` and raw `"K"`+number prefixing OUTSIDE `packages/i18n`. Deterministic, no network.
- **`pseudo.ts`:** generate `en-XA` by bracketing + accenting every EN value (e.g. `[!!Ħömé!!]`) so any un-keyed raw-EN string is visually obvious; wire it as a build-time locale that CI can smoke-render. Keep it dev/CI-only (not shipped to prod locales).
- **`perf.yml`:** add a step (blocking) running the sweep; keep the existing bundle/lighthouse jobs + the `2.109.1`-style pins and structure intact — additive edit only.
- **Fixes:** for each real violation, apply the correct next-intl key (append to the right EXISTING namespace; do NOT invent namespaces). If clean, say so.

## 5–9. Security etc.

Sweep is deterministic + offline; missing-key detection prevents runtime `MISSING_MESSAGE`; formatK-bypass grep protects the money-format invariant; pseudo-locale is dev/CI-only (never a prod locale); perf.yml edit additive; no secrets.

## 10. Tests (RUN before reporting)

`node scripts/ci/i18n-lint.mjs` exits 0 on a clean tree (after your fixes) and non-zero on a seeded violation (add a fixture proving teeth — hardcoded string + missing key + formatK bypass each caught). Pseudo-locale smoke: `en-XA` renders a screen with every string bracketed (no raw EN). `pnpm --filter customer build/typecheck/lint`. Validate perf.yml parses (yaml load).

## 11. Acceptance criteria / DoD

- [ ] Sweep catches template/aria/meta hardcoded strings + missing keys + formatK bypasses (fixture proves teeth); zero real violations remain (or documented-deferred in `i18n-audit.md`); pseudo-locale renders every screen bracketed.
- [ ] Wired blocking into `perf.yml` (additive); customer build green; no ci.yml/sibling-file churn.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P03 — i18n completeness & formatting audit
**STATUS/FILES/DEVIATIONS** (what the sweep covers beyond the eslint rule; the missing-key diff approach; violations found + fixed vs deferred; the perf.yml step) **/TESTS** (paste sweep-clean + sweep-catches-fixture + pseudo-locale smoke + perf.yml yaml-ok) **/EXCERPTS** the sweep's three checks + the perf.yml step — nothing else **/QUESTIONS** (list any violation you deferred because a sibling owns the file)
