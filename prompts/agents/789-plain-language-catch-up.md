# Task: bring PR #789 (plain-language pass) up to date with `master`

**Agent:** Cursor (model: Grok 4.7 or Composer 2.5, not Claude, GPT or Gemini, which are billed extra)
**Branch:** `feat/simple-ux-literacy` (PR #789). Push to this same branch. Never push to `master`.
**Reviewer:** Claude merges once CI is green. Do not merge it yourself.
**Board:** before starting, set the #789 row in `docs/ops/agent-board.md` to `in progress — cursor`. When done, set it to `ready for review` and add one line of notes.

## Why

#789 rewrote customer- and vendor-facing text in plain language. Since then `master` gained loyalty Points, branches, plans, trials, extras, coupons and the unified checkout, so 29 files now conflict, most of them i18n JSON.

## Steps (Windows PowerShell, in `C:\Users\User\Documents\Convergeo-release`)

```powershell
git fetch origin
git checkout feat/simple-ux-literacy
git pull --ff-only origin feat/simple-ux-literacy
git merge origin/master
```

Resolve every conflict with these rules:

1. **`packages/i18n/messages/*/*.json`:** keep the **union of keys**. A key that exists on only one side stays. A key that exists on both sides takes **#789's plain-language wording** when it rewords the same meaning, and **master's wording** when master changed the meaning (for example, new placeholders like `{count}` or `{points}`, or new features). Every ICU placeholder in the English string must also appear in every other locale of that key. The JSON must parse; check with `node -e "JSON.parse(require('fs').readFileSync(process.argv[1]))" <file>`.
2. **`PHASE1_NATIVE_REVIEW.md`:** keep both sides' entries.
3. **`.tsx` components** (`shop-header.tsx`, `header-theme-toggle.tsx` and others): keep master's structure and features (new props, flags, components) and apply #789's wording only through i18n keys. Never hardcode strings, because lint enforces i18n.
4. **Tests (`*.test.tsx` / `*.test.ts`):** keep master's tests. Update expected text to the final i18n strings.
5. Do not touch `supabase/migrations/`, `scripts/ci/` or `services/api/` unless a conflict sits there; if one does, stop and write it on the board for Claude.

Then:

```powershell
git add -A
$env:LEFTHOOK=0; git commit --no-edit; Remove-Item Env:LEFTHOOK
pnpm i --frozen-lockfile
pnpm --filter customer typecheck; pnpm --filter vendor typecheck
pnpm --filter customer lint; pnpm --filter vendor lint
pnpm --filter customer test; pnpm --filter vendor test
pnpm --filter @vergeo5/i18n test
```

Fix only failures the merge caused. Then `git push origin feat/simple-ux-literacy`. **No `--force`.**

## Done means

- No conflict markers remain (`git grep -n "<<<<<<<"` is empty).
- Typecheck, lint and tests are green locally for customer, vendor and i18n.
- Pushed, and the PR #789 checks are running.
- The board row is updated with what you changed and anything you were unsure about.
