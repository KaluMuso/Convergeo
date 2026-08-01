> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P08 — Widen the locale parity gate; make review a recorded fact

## 1. Context

**Wave R2-C. Depends on R02-P06 and R02-P07.**

### 1.1 The gate already exists and is already good

`scripts/check_phase1_overlays.py` (run by `pnpm --filter @vergeo/i18n test`) asserts, for `bem` and
`nya`, that every Phase-1 critical key is **present**, that **ICU placeholders match English**, and
that the value is **not an accidental English copy** — with a brand-token allowlist for legitimate
matches like `MTN`, `MoMo`, `K`, `Vergeo5`. The TS mirror lives at `packages/i18n/src/phase1-critical.ts`
(`isUnexpectedEnglishFallback:154`, `PHASE1_ENGLISH_ALLOWLIST:105`).

**Do not rebuild any of that.** It runs green today:

```
$ python3 scripts/check_phase1_overlays.py
OK: all Phase-1 critical keys present, ICU matched, not accidental English
```

### 1.2 Why green is compatible with 31% translated

The gate protects a deliberately narrow purchase-journey slice, and some namespaces are represented by
a token prefix or two while the namespace as a whole is mostly English:

| Namespace   | Critical prefixes guarded               | Namespace translated-share |
| ----------- | --------------------------------------- | -------------------------- |
| `marketing` | `notFound`, `error` — **2 prefixes**    | **9%**                     |
| `account`   | `title`, `nav`, `locales`, `common` — 4 | **35%**                    |
| `orders`    | 12 prefixes                             | 28%                        |
| `catalog`   | 22 prefixes                             | 62%                        |

That is not a broken gate; it is a gate whose scope was set for a narrower Phase-1 than the surface the
product now ships. Widening it is a **deliberate act with a cost** — every prefix added is a promise
that a human keeps those keys translated, forever, or CI goes red.

### 1.3 What R02-P06 and R02-P07 leave for this pebble

- **P06** single-sourced the prefix table (three drifting copies before: TS, `check_phase1_overlays.py`,
  `generate_phase1_overlays.py` — the enforcing checker was missing `catalog.home.serviceBar`) and made
  the generator merge instead of overwrite. **Confirm that landed before you widen anything**; widening
  a gate whose generator still overwrites would make CI red on work that a script then deletes.
- **P07** produced candidate translations and `docs/plan/i18n-review-worksheet.md` with **every
  sign-off line blank**, and deliberately left `checkout` alone (D27 forbids unreviewed money copy).

**Type:** `[CODE]` — CI gate + a durable ledger. **No translation content.**

## 2. Objective & scope

Widen the parity gate to the coverage the product actually ships, and turn "human-reviewed" from an
aspiration in D27 into a fact recorded in the repo and checkable in CI.

**Non-goals — do NOT do these:**

- **Do not add, change or remove a single translated string.** `git diff --stat` on
  `packages/i18n/messages/` must be **empty**. If widening turns the gate red, the fix is a narrower
  widening or a follow-up translation pebble — **never** editing content here.
- **Do not sign off any namespace as reviewed.** Only a human names themselves. An agent writing a
  reviewer's name into the ledger would be fabricating the exact fact D27 depends on.
- Do not weaken `isUnexpectedEnglishFallback` or pad `PHASE1_ENGLISH_ALLOWLIST` to make a widened gate
  pass — that converts a real signal into a rubber stamp. Adding a genuinely locale-neutral token
  (a new network name, a currency symbol) is fine; adding an English sentence is not.
- Do not touch `scripts/generate_phase1_overlays.py` or `export_translation_overrides.py` (R02-P06).
- Do not add `admin.json` / `clips.json` / `legal.json` to the guarded set — operator-facing, dark, and
  deliberately-English respectively.
- Do not add a dependency, a migration, or an API route.

## 3. Files (create/modify ONLY these)

- `packages/i18n/src/phase1-critical.ts` — the single source; widen the prefix set here.
- `packages/i18n/src/phase1-critical.test.ts` — cover the widened set.
- `scripts/check_phase1_overlays.py` — the ledger check; **no second copy of the prefix table** (P06
  made it read the single source — keep it that way).
- `scripts/ci/i18n-lint.mjs` — wire the ledger check into the blocking sweep.
- `.github/workflows/perf.yml` — only if the sweep needs a new invocation line.
- `docs/plan/i18n-review-ledger.md` **(new)** — the durable record.
- `docs/plan/i18n-audit.md` — point at the ledger and state the policy.

**Guardrail: modify ONLY these files.** Nothing under `packages/i18n/messages/`.

## 4. Implementation spec

1. **Widen deliberately, and prove each step.** Extend the guarded prefixes toward full customer-facing
   coverage for the namespaces P07 worked (`marketing`, `orders`, `account`, `directory`, `catalog`,
   `auth`, `search`), and add `directory` to `PHASE1_CRITICAL_NAMESPACES` if it is absent.
   - Work **incrementally**: widen, run the checker, record what fails, decide. Do not widen everything
     and then reverse-engineer an allowlist to make it pass.
   - The honest stopping point is **the widest set that passes on P07's output without weakening any
     check**. Anything beyond that is a promise the repo cannot currently keep.
   - Report exactly which prefixes you added and which you wanted to add but could not, with the key
     counts that would fail. That list is the next translation pebble's scope, and it is one of the
     more valuable things this pebble produces.

2. **`checkout` stays where it is.** Its remaining keys are money copy awaiting native-speaker review
   (D27). Do not widen `checkout` prefixes on the strength of machine-produced strings — that would
   have CI certify precisely what the decision says must be human-certified.

3. **The review ledger.** `docs/plan/i18n-review-ledger.md`: one row per (locale × namespace) with
   reviewer name, date, coverage at review time, and status — `reviewed` / `unreviewed` /
   `deliberately-english`. Seed it from reality, not aspiration:
   - every namespace P07 touched ⇒ **`unreviewed`**;
   - `legal` (both locales) ⇒ **`deliberately-english`**, citing D27 and CR-B;
   - `vendor`, `admin`, `clips` ⇒ operator-facing/dark, out of the customer review scope;
   - **no row may say `reviewed`** when this pebble lands. If every row is `unreviewed` or
     `deliberately-english`, the ledger is correct.

4. **Make the ledger checkable, not decorative.** Add a check — in `check_phase1_overlays.py`, wired
   into the blocking `i18n-lint.mjs` sweep — that parses the ledger and fails when:
   - a locale/namespace pair in the guarded set has **no ledger row** (new namespaces cannot appear
     unrecorded); and
   - a row claims `reviewed` with no reviewer name or no date.

   It must **not** fail merely because a row is `unreviewed` — that is today's honest state and a red
   build for it would just get the check disabled.

5. **State the launch policy in one place.** In `docs/plan/i18n-audit.md`: shipping unreviewed
   vernacular on the **customer money path** is a founder decision (D27), not an engineering default;
   the ledger is where that decision is recorded; and `O14` in
   `docs/plan/r02/01-strategy-convergence.md` §6 is the operational step that closes it.

## 9. Security

- CI and docs only; no runtime code path, no route, no schema.
- The ledger records **names** — a reviewer's name is personal data. Names only, no emails, no phone
  numbers, no NRC references. Zambia DPA applies to a public repo as much as to the database.
- The gate must not be disable-able by an environment variable. A parity gate with a documented escape
  hatch is not a gate.

## 10. Tests (RUN before reporting)

- `python3 scripts/check_phase1_overlays.py` — green with the widened set. Paste the output.
- `pnpm --filter @vergeo/i18n test` — vitest plus the checker.
- `node scripts/ci/i18n-lint.mjs` and `node scripts/ci/i18n-lint.mjs --self-test` — blocking sweep green,
  ledger check wired in.
- **Negative tests, all three pasted:** (a) delete a ledger row for a guarded namespace ⇒ fail;
  (b) set a row to `reviewed` with no name ⇒ fail; (c) revert both ⇒ green.
- Prove the widening has teeth: temporarily replace one newly-guarded Bemba value with its English
  string, confirm the checker fails, revert. Paste it.
- **`git diff --stat -- packages/i18n/messages/` must be empty.** Paste it.

## 11. Acceptance criteria / DoD

- [ ] Prefix set widened **incrementally**, with the added set and the could-not-add set both reported
      with failing key counts.
- [ ] Still exactly **one** source for the prefix table; no second copy reintroduced.
- [ ] `isUnexpectedEnglishFallback` unweakened; allowlist additions (if any) are genuinely
      locale-neutral tokens, each justified in the report.
- [ ] `checkout` prefixes **not** widened; reason stated.
- [ ] Ledger exists, covers every guarded locale × namespace, and contains **no `reviewed` row**.
- [ ] Ledger check wired into the blocking sweep; all three negative tests demonstrated.
- [ ] Widening proven to have teeth by the English-substitution test.
- [ ] Launch policy for unreviewed money-path vernacular stated once, in `i18n-audit.md`, pointing at
      the ledger and O14.
- [ ] **No translated string changed** — `git diff --stat -- packages/i18n/messages/` empty.
- [ ] No dependency, migration or API route; no environment-variable escape hatch.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P08 — Locale parity gate + review ledger
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the checker output, the i18n-lint sweep, all three ledger negative tests, the
English-substitution teeth test, and `git diff --stat -- packages/i18n/messages/`
**WIDENED:** the prefixes added, per namespace
**COULD NOT WIDEN:** the prefixes you wanted but could not, with failing key counts — this is the next
translation pebble's scope
**ALLOWLIST:** any token added, with justification (or "none")
**LEDGER:** confirm explicitly that no row says `reviewed`
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
