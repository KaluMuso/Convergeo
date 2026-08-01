> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P07 — Bemba / Nyanja: customer namespaces (candidates, explicitly unreviewed)

## 1. Context

**Wave R2-C. Depends on R02-P06** — do not start until the merge-not-overwrite fix has landed, or your
work can be destroyed by one `generate_phase1_overlays.py` run.

**Read this first: you cannot finish this pebble alone, and you must not pretend to.** D27 mandates
**human-reviewed** Bemba and Nyanja. No agent can certify either language. This pebble produces
**candidates plus a reviewer worksheet**; a native speaker converts them into shipped copy. The DoD
below forbids marking anything reviewed.

### 1.1 Measured state (this tree, counted leaf-by-leaf against English)

Bemba: **2373 of 4044** English keys present (58.7%), of which **1120 are byte-identical to English** ⇒
**1253 genuinely translated (31.0%)**. Nyanja is within a few keys of identical.

| Namespace         | EN keys  | translated | share   | In this pebble?                 |
| ----------------- | -------- | ---------- | ------- | ------------------------------- |
| `marketing`       | 135      | 12         | **9%**  | **yes** — worst customer gap    |
| `orders`          | 162      | 46         | **28%** | **yes** — post-purchase         |
| `account`         | 202      | 71         | **35%** | **yes**                         |
| `directory`       | 79       | 36         | 46%     | **yes**                         |
| `catalog`         | 273      | 168        | 62%     | **yes** — core discovery        |
| `auth`            | 89       | 58         | 65%     | **yes**                         |
| `search`          | 76       | 57         | 75%     | **yes**                         |
| `checkout`        | 215      | 161        | 75%     | **NO — see §1.2**               |
| `legal`           | 128      | 0          | 0%      | **NO** — deliberate             |
| `vendor`          | 1161     | 235        | 20%     | **NO** — operator-facing        |
| `admin` / `clips` | 915 / 85 | 0          | 0%      | **NO** — operator-facing / dark |

### 1.2 Why `checkout` is excluded

D27, verbatim: machine translation is "allowed for long-tail listing content with an 'auto-translated'
tag, **never for checkout/payment/legal copy without review**." Checkout copy is money copy. The
remaining 47 keys stay for the reviewed lane — filling them here would be the one thing the decision
explicitly forbids. **Do not touch `checkout.json` in any locale.**

`legal` stays English by the same logic plus a liability judgement already recorded in
`docs/plan/concept-code-reconciliation-2026-07-21.md` and `prompts/fixes/CR-B-i18n-bem-nya-parity.md`.

### 1.3 Prior art — this is a continuation, not a fresh start

`prompts/VF-P01-bemba-nyanja-translations.md` and `prompts/fixes/CR-B-i18n-bem-nya-parity.md` cover
this ground and were **partially executed** — that is where today's 31% came from. Both demanded human
review; **neither has a review record anywhere in the repo.** Read them before starting and match their
terminology decisions rather than inventing a second vocabulary.

### 1.4 The quality problem to avoid repeating

Existing strings are heavily code-switched. Verbatim from `packages/i18n/messages/bem/vendor.json`:

> `"Moniteni ukuteka kwenu, orders, and cart activity over the last 7 or Masiku 30"`

Half-translated sentences read worse than clean English and are harder for a reviewer to repair than
an honest gap. **Consistency and restraint beat volume here.** A key you cannot translate confidently
is better left absent — it falls back to English cleanly (`packages/i18n/src/request.ts` deep-merge)
and appears on the worksheet for the reviewer.

**Type:** `[CODE + HUMAN REVIEW]` — the agent half is candidates and tooling output; the human half is
the actual language.

## 2. Objective & scope

Raise genuine Bemba/Nyanja coverage on the seven customer namespaces above, with every new string
marked unreviewed and every string the agent could not confidently produce recorded for the reviewer.

**Non-goals — do NOT do these:**

- **Do not touch `checkout.json`, `legal.json`, `vendor.json`, `admin.json` or `clips.json`** in any
  locale, for the reasons in §1.1–§1.2.
- **Do not touch any file under `packages/i18n/messages/en/`.** English is the source of truth; if a
  key is missing there, report it.
- **Do not add or remove keys relative to English.** Key sets mirror `en/` exactly.
- **Do not mark anything reviewed**, and do not write a reviewer's name anywhere.
- **Do not widen the Phase-1 critical prefix set** (R02-P08) or edit `scripts/ci/i18n-lint.mjs`,
  `.github/workflows/perf.yml`, `phase1-critical.ts`, or either overlay script (R02-P06/P08 own them).
- Do not translate placeholder names, ICU argument names, or brand tokens.

## 3. Files (create/modify ONLY these)

- `packages/i18n/messages/bem/{marketing,orders,account,directory,catalog,auth,search}.json`
- `packages/i18n/messages/nya/{marketing,orders,account,directory,catalog,auth,search}.json`
- `docs/plan/i18n-review-worksheet.md` **(new)** — the reviewer's task list.

**Guardrail: exactly these 14 message files plus the worksheet.** Nothing else.

## 4. Implementation spec

1. **Terminology first, strings second.** Before translating, extract the vocabulary already in use in
   the existing bem/nya files for recurring product nouns — order, listing, escrow, delivery, pickup,
   vendor, cart, ticket. Put that glossary at the top of the worksheet and **use it consistently**. A
   reviewer can fix a wrong-but-consistent term with one find-and-replace; inconsistent terms must be
   fixed one by one.

2. **Whole sentences or nothing.** Never mix languages inside one string. If a term has no natural
   Bemba/Nyanja equivalent in common Lusaka usage (many technical/commerce terms genuinely do not),
   prefer the borrowed term used naturally in speech over an invented calque — and record the choice
   in the glossary so the reviewer can overrule it once, globally.

3. **ICU integrity is non-negotiable.** Placeholder sets must match English exactly — same names, same
   count. Plural/select structures must remain valid ICU for the target locale. A dropped `{amount}`
   or a broken plural is a **review-blocking bug**, not a translation nit. The overlay checker verifies
   placeholder parity for Phase-1 critical keys (`extractIcuPlaceholders`); everything else is on you.

4. **Leave a gap rather than guess.** For any key you cannot render as a confident whole sentence, omit
   it (English fallback is clean and silent) and list it in the worksheet under its namespace. **A
   large, honest gap list is a successful outcome for this pebble**, not a failure — it is the
   reviewer's job queue.

5. **The worksheet.** `docs/plan/i18n-review-worksheet.md` must contain: the glossary and its open
   questions; per namespace, the keys filled as candidates and the keys deliberately left open; the
   money/legal exclusions and why; and a blank sign-off line per namespace per locale for the reviewer
   to complete. **Leave every sign-off line blank** — R02-P08 turns this into the durable ledger.

6. **Do not run the generator.** `scripts/generate_phase1_overlays.py` holds its own copy of the
   Phase-1 strings; running it will fight your edits even after R02-P06's merge fix, because its
   embedded dicts are stale relative to anything you write. Hand-edit the JSON. If you believe the
   generator's embedded strings need updating, **say so in the report** — that is a follow-up, not
   this pebble.

## 9. Security

- No code, no route, no schema. Content only.
- Never translate a placeholder name (`{amount}`, `{count}`, `{vendor}`) or an ICU argument — that
  silently breaks rendering.
- No user data, no real names, no real phone numbers in any example string.
- Do not alter money formatting: `formatK()` owns currency rendering, and a translated string must
  never inline a `K`-prefixed amount itself (the `formatK` bypass check in `scripts/ci/i18n-lint.mjs`
  is blocking and will catch it).

## 10. Tests (RUN before reporting)

- `pnpm --filter @vergeo/i18n test` — vitest plus `check_phase1_overlays.py`; must stay green.
- `node scripts/ci/i18n-lint.mjs` — blocking sweep, including the `formatK` bypass check.
- `node scripts/ci/i18n-lint.mjs --pseudo-smoke`
- A JSON parse + key-set diff against `en/` for all 14 files: **no added or removed keys**. Paste the
  result.
- An ICU placeholder-parity check across every key you touched, not just the critical ones. Paste the
  count checked.
- `pnpm build --filter customer` — the customer app builds with the new messages.
- Re-run the per-namespace translated-share count from §1.1 and paste the before/after table.
- Confirm `git diff --exit-code -- packages/i18n/messages/en packages/i18n/messages/bem/checkout.json packages/i18n/messages/nya/checkout.json packages/i18n/messages/bem/legal.json packages/i18n/messages/nya/legal.json` is clean.

## 11. Acceptance criteria / DoD

- [ ] Only the 14 named message files plus the worksheet changed.
- [ ] `checkout`, `legal`, `vendor`, `admin`, `clips` untouched in every locale; `en/**` untouched.
- [ ] No key added or removed relative to English in any touched file.
- [ ] ICU placeholder sets match English for **every** touched key; count reported.
- [ ] No string mixes languages mid-sentence; spot-check evidence in the report.
- [ ] A glossary exists and is applied consistently across both locales.
- [ ] Keys not confidently translatable are **omitted and listed**, not guessed.
- [ ] Worksheet lists filled vs open keys per namespace, with **every sign-off line blank**.
- [ ] Nothing marked reviewed; no reviewer name recorded.
- [ ] `generate_phase1_overlays.py` **not run**; `phase1-critical.ts`, `i18n-lint.mjs` and `perf.yml`
      untouched.
- [ ] Before/after translated-share table reported per namespace and locale.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P07 — Bemba / Nyanja customer namespaces (candidates)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the overlay checker, i18n-lint, key-set diff, ICU parity count, and the before/after
translated-share table
**EXCERPTS:** the glossary, and five representative translated strings per locale with their English
source side by side
**GAPS LEFT OPEN:** count per namespace, and the reason category (no natural term / needs context /
money-adjacent)
**CONFIDENCE:** state plainly how confident you are in the output and what a native speaker should
check first. Do not overstate this.
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
