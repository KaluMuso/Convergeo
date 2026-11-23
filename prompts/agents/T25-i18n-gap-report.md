# Task T25: i18n report: untranslated English in bem, nya, fr, zh (docs only)

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/i18n-gap-report` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T25 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `docs/ops/i18n-gaps-2026-wk48.md` (new). No other file.

## Problem

bem and nya are partial and fall back to English at runtime; some fr and zh values are still English text. We need an honest list before paying for real translation. Do not machine-translate or edit any message file.

## Steps

1. Namespaces to cover (customer-facing): account, orders, checkout, catalog, nav, search, auth, common, marketing, directory, events, services, notifications, clips. Files: `packages/i18n/messages/<locale>/<ns>.json`. Skip admin, vendor, ai, legal.
2. For each locale and namespace, count: (a) keys missing vs en, (b) keys present but identical to en with more than 12 characters (likely untranslated). Use a throwaway script in your scratch space; don't commit it. Brand names, URLs and ICU-only values don't count.
3. Write the report: a summary table (locale x namespace: missing / identical), then per locale the top 10 most user-visible gaps (key and English text), ordered by flow: checkout, orders, account, search, catalog.
4. End with a short recommendation: which two namespaces to translate first for bem and nya, and how many strings that is. Note that `clips` has no files in bem, nya, fr, zh.

## Done means

The report exists, numbers match a re-run of your script, no JSON changed, and `pnpm exec prettier --check docs/ops/i18n-gaps-2026-wk48.md` passes. No tests needed (docs only).

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
