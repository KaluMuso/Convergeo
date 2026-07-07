> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P08 — Supabase pipeline & base migration (Wave 0 gap-fill)

## 1. Context
Wave 0 merged (PRs #3–#19) from an earlier pebble decomposition that **did not include the Supabase pipeline** — the canonical plan's M01-P03. This pebble fills that gap; it **blocks all schema pebbles** (M03-*, dispatching in Wave 1 batch B). As-built repo state you can rely on: monorepo tooling at root + `packages/config`, `packages/{i18n,types}` skeletons exist (`packages/types/src/index.ts` has a placeholder `Database` type), FastAPI service in `services/api`, CI in `.github/workflows/ci.yml` (jobs: js, python, gitleaks, deps-audit, i18n-lint). There is **no `supabase/` directory yet**. Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P03 (canonical numbering).

## 2. Objective & scope
Supabase CLI local stack config, migration `0001_extensions.sql`, typegen script writing `packages/types/src/db.ts`, workflow doc, and a **new `db` job in CI** (db reset + typegen drift check).
**Non-goals:** no domain tables (M03 owns all schema), no RLS policies yet, no seed data, no Supabase JS client wiring in apps.

## 3. Files (create/modify ONLY these)
- **Create:** `supabase/config.toml` · `supabase/migrations/0001_extensions.sql` · `scripts/gen-types.sh` · `packages/types/src/db.ts` (generated output, committed) · `docs/ops/supabase-workflow.md`
- **Modify:** `packages/types/src/index.ts` (re-export the generated `Database` type from `./db`, replacing the placeholder) · `packages/types/package.json` (add `gen:types` script) · `.github/workflows/ci.yml` (**add the `db` job only — do not restructure existing jobs**)
**Guardrail: touch nothing else; anything more → DEVIATIONS. Add NO new npm dependencies (Supabase CLI is invoked as an external binary/npx — keep `pnpm-lock.yaml` untouched so parallel Wave-1 pebbles don't conflict on it).**

## 4. Implementation spec
- **`0001_extensions.sql`:** `create extension if not exists` for `pgcrypto`, `pg_trgm`, `vector`. Nothing else.
- **Migration convention (document it):** one migration per pebble, `NNNN_slug.sql`, numbers pre-assigned in prompts (0002 identity/vendors, 0003 catalog, 0004 services/events, 0005 orders, 0008 config, 0009 search…); **additive-only after M03-P08 merges**.
- **`scripts/gen-types.sh`:** runs `supabase gen types typescript --local` → `packages/types/src/db.ts`; `--project-id` variant for staging documented; fails loudly (non-zero) if the CLI or local stack is unavailable. Committed types are source of truth.
- **CI `db` job:** Supabase CLI setup (official action or binary download), `supabase db reset` against the local stack, run `scripts/gen-types.sh`, then `git diff --exit-code packages/types/src/db.ts` — **stale committed types fail the job**. Independent of existing jobs; least-privilege permissions preserved.
- **`docs/ops/supabase-workflow.md`:** local stack up/reset, diff→new migration, push to staging/prod, typegen step, env/secret **names only**, additive-only rule, and the note that service-role key is server-only (anon key is the only browser-safe key).

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A.

## 9. Security
No project refs, tokens, or keys committed anywhere — placeholders + env names only. `config.toml` is local-dev config only.

## 10. Tests (RUN before reporting)
- `supabase db reset` clean with `0001` applied; verify `select extname from pg_extension` shows all three extensions (paste output).
- `scripts/gen-types.sh` produces a `db.ts` that compiles: `pnpm --filter @vergeo/types typecheck`.
- `bash -n scripts/gen-types.sh`.
- Drift-check simulation: hand-edit `db.ts`, confirm the CI drift command fails, regenerate, confirm it passes.
- Full repo still green: `pnpm typecheck`, `pnpm test`, YAML-validate the edited `ci.yml`.

## 11. Acceptance criteria / DoD
- [ ] `supabase db reset` clean; extensions active.
- [ ] Typegen output compiles; `@vergeo/types` exports `Database` from the generated file.
- [ ] CI `db` job exists: reset + typegen drift check (stale types fail — demonstrated).
- [ ] Workflow doc is copy-pasteable for a fresh session; migration numbering + additive-only rule documented.
- [ ] No secrets committed; no new npm deps; `pnpm-lock.yaml` untouched.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P08 — Supabase pipeline & base migration (gap-fill)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual db reset / typegen / drift-check / typecheck output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
