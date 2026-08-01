> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P06 — Translation workbench: stop the overwrite, single-source the prefixes, land the export

## 1. Context

**Wave R2-C.** Source: `docs/plan/r02/01-strategy-convergence.md` §3.7, §5. **Reshaped from the
discovery doc's original P06 after reading the tooling** — see §1.3.

### 1.1 The landmine

`scripts/generate_phase1_overlays.py` holds Bemba and Nyanja strings as Python dicts (`BEM:130`,
`NYA:557`) and writes them into the message files with `out_path.write_text(...)` (`write_overlays:982`)
— a **full file overwrite containing only the Phase-1 critical keys**. Every non-critical translation
in those namespaces is silently destroyed.

Measured against the current tree, one `python3 scripts/generate_phase1_overlays.py` run destroys
**196 existing translations**:

| File               | keys now | keys after | lost   |
| ------------------ | -------- | ---------- | ------ |
| `bem/account.json` | 72       | 21         | **51** |
| `bem/catalog.json` | 175      | 150        | 25     |
| `bem/search.json`  | 68       | 51         | 17     |
| `bem/common.json`  | 25       | 20         | 5      |
| _(nya: identical)_ | —        | —          | 98     |

The script is committed, executable, unguarded, and named as though running it were routine. It is the
single most dangerous file in the i18n tree and nothing in the repo warns anyone.

### 1.2 The prefix table exists three times and has already drifted

| Copy                                   | Role                                                       |
| -------------------------------------- | ---------------------------------------------------------- |
| `packages/i18n/src/phase1-critical.ts` | exported for TS consumers                                  |
| `scripts/check_phase1_overlays.py`     | **the enforcing gate** (`pnpm --filter @vergeo/i18n test`) |
| `scripts/generate_phase1_overlays.py`  | the generator's own `PREFIXES`                             |

The Python checker's comment says "Mirror `packages/i18n/src/phase1-critical.ts`". It no longer does:
TS declares `catalog.home.serviceBar`, the **enforcing gate does not** — so a prefix the codebase
believes is protected is unprotected. The generator has a third shape again (`common` includes `nav`,
`catalog` includes `home.nav`).

### 1.3 What already works — do not rebuild it

- The gate is real, wired and **currently green**: `python3 scripts/check_phase1_overlays.py` →
  `OK: all Phase-1 critical keys present, ICU matched, not accidental English`. It checks presence,
  ICU placeholder parity, **and** that a value is not an accidental English copy
  (`isUnexpectedEnglishFallback`, `phase1-critical.ts:154`), with a brand-token allowlist.
- Missing keys fall back to English at runtime by design (`packages/i18n/src/request.ts` deep-merge) —
  nothing renders a raw key path.
- `translation_overrides` (`supabase/migrations/0053`) plus `routers/admin_translations.py` and the
  admin `TranslatorView` (`apps/admin/app/[locale]/translations/`) give admins an authoring surface.

**The gate being green while Bemba is 31% genuinely translated is not a bug in the gate** — its prefix
set is a deliberately narrow purchase-journey slice. Widening it is **R02-P08**, not this pebble.

### 1.4 The missing link

`0053`'s header states the workflow: "Admins edit here, then **export the merged result back into
`packages/i18n/messages/<locale>/<namespace>.json`**." `admin_translations.py:5` repeats it. **No such
export exists.** A native speaker can author translations in the admin UI today and has no supported
way to get them into the files the apps actually bundle.

**Type:** `[CODE]` — tooling only. **No message-content changes, no migration.**

## 2. Objective & scope

Make the translation workbench safe to use and capable of landing a human's work. This pebble writes
**no translations** — it makes R02-P07 and the native-speaker review possible without data loss.

**Non-goals — do NOT do these:**

- **Do not add, change or remove a single translated string** in any `packages/i18n/messages/**` file.
  `git diff --stat` on that path must show **zero changes** (except a file the export tooling round-trips
  byte-identically, which is not a change).
- **Do not widen the Phase-1 critical prefix set** — R02-P08 owns that, deliberately, with review.
- **Do not touch `scripts/ci/i18n-lint.mjs` or `.github/workflows/perf.yml`** — R02-P08 owns them.
- Do not change `isUnexpectedEnglishFallback`, the allowlist, or the gate's semantics.
- Do not add a migration, an API route, or a dependency.
- Do not machine-translate anything.

## 3. Files (create/modify ONLY these)

- `scripts/generate_phase1_overlays.py` — make it safe.
- `scripts/check_phase1_overlays.py` — consume the single source instead of its own copy.
- `packages/i18n/src/phase1-critical.ts` — becomes the single source; **prefix values unchanged**.
- `scripts/i18n_prefixes.py` **(new, if needed)** — the loader that lets Python read the TS source
  without a JS runtime.
- `scripts/export_translation_overrides.py` **(new)** — the missing `translation_overrides` → JSON path.
- `services/api/tests/test_export_translation_overrides.py` **(new)**
- `docs/plan/i18n-audit.md` — a short section documenting the workbench and its hazards.

**Guardrail: modify ONLY these files.** Nothing under `packages/i18n/messages/**`.

## 4. Implementation spec

1. **Stop the overwrite.** `write_overlays` must **merge** into the existing file, never replace it:
   read the current locale JSON, deep-merge the critical overlay over it, write the union. Existing
   non-critical keys survive.
   - Add a `--check` / dry-run mode that prints what _would_ change and **exits non-zero if any
     existing key's value would be lost or altered**. Make this the default in CI-ish contexts.
   - Print a loud summary of keys preserved vs written, so the operator sees the merge happened.
   - Add a regression test — or a self-check the script runs — that constructs a locale file with an
     extra non-critical key and proves it survives a run. **This is the single most important
     assertion in the pebble.**

2. **Single-source the prefix table.** Pick `packages/i18n/src/phase1-critical.ts` as the source (it is
   the one the TS build type-checks) and have both Python scripts read it, parsing the exported object
   rather than restating it. If a robust parse is impractical, the fallback is a generated JSON
   artifact committed alongside, plus a test that fails when TS and the artifact disagree — **what is
   not acceptable is three hand-maintained copies**.
   - **Preserve every current prefix value exactly.** Reconciling the existing `home.serviceBar` drift
     means the enforcing gate gains a prefix it did not check before, so **run the gate afterwards**;
     if that newly-enforced prefix now fails, **report it, do not fix it by editing translations** —
     that content work belongs to R02-P07.

3. **Export path.** `scripts/export_translation_overrides.py` reads `translation_overrides` (locale,
   namespace, message_key, value) and merges the rows into the corresponding message JSON.
   - **Merge, never replace** — same rule as above, same dry-run, same loss guard.
   - Refuse to write a key that does not exist in `en/<namespace>.json`: an override for a
     non-existent key is a typo, and silently creating it produces a key nothing renders.
   - Preserve ICU placeholders — reuse the existing placeholder extraction
     (`extractIcuPlaceholders`, `phase1-critical.ts:143`) or mirror it, and **refuse** an override
     whose placeholder set differs from English. A translation that drops `{amount}` is a money bug.
   - Deterministic output: same key order and formatting as the existing files, so a diff shows
     translation changes and nothing else.
   - Read-only against the database. Never write to `translation_overrides`.

4. **Document the workbench.** In `docs/plan/i18n-audit.md`: which file is the source of truth for
   which keys, the merge-not-overwrite rule, how a native speaker's work flows from the admin UI into
   the repo, and an explicit warning about the historical overwrite behaviour so nobody reintroduces it.

## 9. Security

- The export script is **read-only** against Postgres. No DSN, service-role key or token in any
  committed file — names only, from the environment.
- `translation_overrides` is admin-authored content that ends up in bundled UI copy. The script must
  not interpret it: no HTML, no markup expansion, no eval. Values land as strings; ICU parity is the
  only structural check.
- Do not log override values wholesale in a way that would dump user-authored content into CI logs —
  counts and keys are enough.

## 10. Tests (RUN before reporting)

- **The loss test:** add a non-critical key to a scratch copy of a locale file, run the generator, prove
  the key survives. Paste it.
- `python3 scripts/generate_phase1_overlays.py --check` (or equivalent) on the current tree —
  must report **no losses** and exit zero.
- `python3 scripts/check_phase1_overlays.py` — still `OK`, or a precisely-reported new failure caused
  by the `home.serviceBar` reconciliation (report, do not fix).
- `pnpm --filter @vergeo/i18n test` (runs vitest + the overlay checker).
- `node scripts/ci/i18n-lint.mjs` — unchanged and green.
- `uv run pytest services/api/tests/test_export_translation_overrides.py` — cover: merge preserves
  existing keys; unknown key refused; ICU placeholder mismatch refused; dry-run writes nothing;
  round-trip is byte-identical when there are no overrides.
- `uv run ruff check .` · `uv run mypy app tests scripts`
- **`git diff --stat -- packages/i18n/messages/` must be empty.** Paste it.

## 11. Acceptance criteria / DoD

- [ ] `generate_phase1_overlays.py` **merges**; a non-critical key demonstrably survives a run.
- [ ] A dry-run/check mode exits non-zero when any existing value would be lost or altered.
- [ ] The prefix table has **one** source; both Python scripts consume it; no hand-maintained third copy.
- [ ] Every current prefix value preserved; the `home.serviceBar` drift is reconciled and its effect on
      the gate **reported**, not papered over by editing translations.
- [ ] `export_translation_overrides.py` merges overrides, refuses unknown keys, refuses ICU mismatches,
      is read-only against the DB, and has a dry-run.
- [ ] `docs/plan/i18n-audit.md` documents the workbench, the merge rule, and the historical hazard.
- [ ] **No translated string added, changed or removed** — `git diff --stat` on
      `packages/i18n/messages/` is empty.
- [ ] `scripts/ci/i18n-lint.mjs` and `.github/workflows/perf.yml` untouched.
- [ ] No migration, no API route, no dependency.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P06 — Translation workbench safety
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the loss test, the generator `--check` output, the overlay checker output, and
`git diff --stat -- packages/i18n/messages/`
**EXCERPTS:** the merge implementation, and the ICU-mismatch refusal
**PREFIX SOURCE:** state which file is now the single source and how each consumer reads it
**SERVICEBAR:** state what happened when the enforcing gate gained `catalog.home.serviceBar`
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
