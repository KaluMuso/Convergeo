# i18n completeness & formatting audit (M16-P03)

Repo-wide i18n completeness sweep + `en-XA` pseudo-locale. Blocking gate wired
into `.github/workflows/perf.yml`. Sweep source: `scripts/ci/i18n-lint.mjs`.
Pseudo generator: `packages/i18n/pseudo.ts`.

## What the sweep covers (beyond the eslint rule)

The existing eslint rule `packages/config/eslint-rules/no-hardcoded-strings.js`
(WARN job in `ci.yml`) flags JSX **text** nodes and a few user-facing
string-literal attributes (`placeholder`/`title`/`alt`/`aria-label`). This sweep
is **blocking** and adds the coverage that rule lacks, in three deterministic,
offline checks:

1. **Hardcoded strings — template / aria / meta.**
   - **Template literals** in user-facing attributes (`title={`Delete ${x}`}`),
     with `${…}` interpolations stripped first so attributes composed purely of
     translated vars are not false-positives.
   - The **full `aria-*` text family** (`aria-label`, `aria-description`,
     `aria-placeholder`, `aria-roledescription`, `aria-valuetext`), not just
     `aria-label`.
   - **`<meta content="…">`** copy (SEO/OG descriptions).
   - JSX **text** nodes are intentionally **left to the eslint rule** — a regex
     text pass cannot separate copy from TS generics (`Promise<T>`) without an
     AST, so the sweep owns only what it can decide deterministically.

2. **Missing keys (used vs defined).** Collects `useTranslations` /
   `getTranslations` / `createTranslator` scopes and every static `t("…")` /
   `t.rich/raw/markup/has("…")` key in a file, then diffs against the keys
   **defined** in `packages/i18n/messages/en/*.json`.
   - Defined keys are flattened to match the runtime provider, which mounts each
     file under `messages[namespace]`. Files mix **nested objects**
     (`home: { nav: { home } }`) and **flat dotted keys that already repeat the
     namespace** (`"ai.ask.title"`); both interpretations are registered so
     resolution matches next-intl.
   - A key is a violation only when it is undefined under **every** scope
     declared in its file (union-of-scopes) — this keeps the check
     **false-positive-free** across the 1.5k statically-resolved usages while
     still catching genuinely-absent keys and the seeded fixture. Dynamic keys
     (`t(`a.${x}`)`) and files whose scope arrives via prop/hook are skipped.
   - Used-but-undefined ⇒ **error**. Defined-but-unused ⇒ advisory log only
     (server-composed footer/legal/email copy and ICU sub-parts are referenced
     indirectly).

3. **formatK bypass (money-format invariant).** Flags, **outside
   `packages/i18n`**, raw `K`-prefixed currency templating (`` `K${…}` ``),
   `"K" + number` concatenation, and `Intl.NumberFormat`. This protects the
   single money-format seam `formatK()`. Date formatting
   (`Intl.DateTimeFormat` / `.toLocaleString`) is a **separate** concern and is
   intentionally **not** flagged here (there are ~25 legitimate locale-aware
   date usages; money is the invariant this gate defends).

The sweep exits non-zero on any real violation. `--self-test` runs it against a
committed fixture (`scripts/ci/__fixtures__/i18n/bad-fixture.tsx`) seeded with one
of each violation and asserts all three detectors still fire — proving teeth on
every CI run.

## Pseudo-locale (`en-XA`)

`packages/i18n/pseudo.ts` accents every EN value and wraps it in `[!! … !!]`
(e.g. `Home → [!!Ĥöɱé!!]`), preserving ICU `{…}` placeholders/plural
sub-messages. Any string that reaches a screen **without** going through
next-intl shows as bare, un-bracketed ASCII — an instant visual coverage gap.
`en-XA` is **dev/CI-only**: it is deliberately **not** added to `LOCALES`
(`packages/i18n/src/locales.ts`) and never ships as a production locale.

The CI smoke is `node scripts/ci/i18n-lint.mjs --pseudo-smoke` (mirrors the
transform in plain JS because CI pins Node 20 via `.nvmrc` and cannot execute
TypeScript directly). It pseudo-localizes all EN namespaces, asserts **every
leaf is bracketed**, renders a sample screen, and includes a control assertion
that a raw EN string is **not** classified as pseudo.

## CI wiring

`.github/workflows/perf.yml` gains one **blocking**, additive step immediately
after `Install dependencies` (pure-node + offline ⇒ fails fast before the
Supabase/build steps):

```yaml
- name: i18n completeness sweep (blocking)
  run: |
    node scripts/ci/i18n-lint.mjs --self-test
    node scripts/ci/i18n-lint.mjs --pseudo-smoke
    node scripts/ci/i18n-lint.mjs
```

`ci.yml`'s existing i18n-lint WARN job is untouched. The bundle-guard,
image-lint, and Lighthouse steps are unchanged.

## Findings

### Fixed

| #   | File                                                             | Issue                                                                                                                                                           | Fix                                                                       |
| --- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 1   | `apps/admin/app/[locale]/orders/_components/OrderDetailView.tsx` | Local `formatNgwee()` built money as `` `K${(value / 100).toFixed(2)}` `` — a `formatK` bypass (no thousands separators, not locale-aware, off the money seam). | Removed the local helper; import and use `formatK()` from `@vergeo/i18n`. |

After the fix the sweep is **clean** (0 hardcoded strings, 0 missing keys, 0
formatK bypasses across `apps/`, `services/`, `packages/`).

### Deferred (documented)

| File                                                  | Issue                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Why deferred                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `apps/customer/app/[locale]/account/privacy/page.tsx` | The DPA export/delete page (shipped in **M04-P06**) references an entire `account.privacy.export.*` / `account.privacy.delete.*` key subtree — plus `account.privacy.backToAccount` — that **does not exist** in `account.json`. `account.json` defines a _flat_ `privacy` block (`title`, `exportCta`, `deleteCta`, `deletePhraseLabel`, …); the page expects nested `export`/`delete` sub-namespaces with different key names (`confirmPhraseLabel`, `otpLabel`, `sendOtp`, `returnToLogin`, `phoneRequired`, `otpSendFailed`, …). ~23 statically-resolvable keys, plus `export`/`delete` `title`/`description` masked by the union-of-scopes rule. This is a genuine, previously-undetected missing-key bug (`messages.test.ts` only validates file presence, not used-vs-defined). | Fixing it means adding ~30 keys of **legally-adjacent DPA copy** to the shared `account` namespace — owned by the account/DPA feature area, not this i18n-tooling QA pebble. Per the parallel-safety rule ("touch only the namespace your prompt assigns") and to avoid inventing sensitive privacy/deletion microcopy, this is tracked here and excluded from the blocking gate via `DEFERRED_MISSING_KEY_FILES` in `scripts/ci/i18n-lint.mjs`. |

**Deferral mechanism:** `DEFERRED_MISSING_KEY_FILES` is a single-file allowlist
for **missing-key detection only** — the hardcoded-string and formatK-bypass
checks still run on the deferred file, and missing-key detection still has full
teeth everywhere else + against the seeded fixture. The list must **shrink,
never grow**.

**Follow-up for the account/DPA owner:** reconcile
`apps/customer/app/[locale]/account/privacy/page.tsx` with `account.json` — add
the `privacy.export.*` / `privacy.delete.*` blocks (or re-scope the page to the
existing flat keys + `account.common.backToAccount` / `account.common.loading`),
then remove the file from `DEFERRED_MISSING_KEY_FILES`.

## Scope notes

- Scanned for hardcoded strings / missing keys: `apps/{customer,vendor,admin}/app`.
  Excluded (not shipped user-facing locale content, matching the eslint rule's
  own ignores): `node_modules`, `.next`, `services/`, tests
  (`.test.`/`.spec.`/`__tests__`), the dev-only component gallery (`(dev)/`
  routes), and this sweep's own `__fixtures__`.
- formatK-bypass scanned repo-wide across `apps/`, `services/`, `packages/`
  (`.ts` + `.tsx`), excluding `packages/i18n` (the money-format seam itself).
