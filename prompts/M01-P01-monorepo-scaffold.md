> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P01 — Monorepo scaffold

## 1. Context
Greenfield repo (only `docs/`, `prompts/`, `CLAUDE.md` exist). **Wave 0, pebble 1 of 7 (sequential)** — the very first code; every later pebble stands on it. Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P01. Read first: `CLAUDE.md`, that pebble spec.

## 2. Objective & scope
pnpm + turborepo workspace with TS-strict base config, shared lint/format presets, turbo pipelines, and Make targets — so `pnpm i` and all root commands run on a fresh clone.
**Non-goals:** no apps, no API, no Supabase (P02–P05), no CI YAML (P06), no infra (P07), no UI tokens.

## 3. Files (create ONLY these)
- Root: `package.json` (private, pinned pnpm via `packageManager`), `pnpm-workspace.yaml`, `turbo.json`, `.gitignore`, `.editorconfig`, `.nvmrc` (Node 20), `Makefile`, `README.md`
- `packages/config/`: `package.json`, `tsconfig.base.json`, `eslint.config.mjs` (flat preset, **incl. a placeholder slot for the no-hardcoded-strings rule** — rule itself lands in M02-P02), `prettier.config.mjs`
**Guardrail: modify ONLY these files; if another file seems to need changes, do not touch it — record it under DEVIATIONS.**

## 4. Implementation spec
- **Workspaces:** `apps/*`, `packages/*`, `services/*` in `pnpm-workspace.yaml`.
- **turbo.json:** pipelines `dev`, `build` (dependsOn `^build`, outputs), `lint`, `typecheck`, `test` — with caching.
- **Root scripts:** `dev|build|lint|typecheck|test` delegate to turbo.
- **tsconfig.base.json:** `strict`, `noUncheckedIndexedAccess`, `moduleResolution: "bundler"`; **no path-alias barrels — deep imports only** (per waves conventions).
- **eslint.config.mjs:** flat config preset consumable by all packages (TS + import order + no-unused); leave a clearly-commented slot where M02-P02 will register `no-hardcoded-strings`.
- **Makefile:** `make dev`, `make test`, `make lint`, `make typecheck`, `make build` wrapping pnpm/turbo.
- **.gitignore:** node_modules, `.next`, `dist`, `.turbo`, `.env*` (keep `.env.example` when it appears in P07), `.venv`, `__pycache__`, coverage, `supabase/.temp`.
- **README.md:** quickstart (install, commands table) + a "Required CI checks" placeholder section (P06 fills it).
- Pin Node (`.nvmrc`) + pnpm (`packageManager` field).

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A (tooling pebble). Keep root dev-deps lean; no heavy postinstall.

## 9. Security
No secrets anywhere; `.gitignore` excludes all `.env*` variants. No registry scripts beyond standard installs.

## 10. Tests
- Add `scripts/ci/check-workspace.mjs` *only if needed*? — **No**: `scripts/ci/` is owned by P06. Instead verify via commands.
- **RUN before reporting:** `pnpm i` (clean), `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` (all succeed as no-ops on the empty workspace), and `pnpm turbo run build --dry-run` (resolves the workspace graph — this is the pebble's CI assertion, paste its output).

## 11. Acceptance criteria / DoD
- [ ] Fresh `pnpm i` clean install.
- [ ] `pnpm lint|typecheck|test|build` execute across (empty) workspaces without error.
- [ ] `turbo run build --dry-run` resolves the graph.
- [ ] Node + pnpm versions pinned; eslint preset exposes the no-hardcoded-strings slot.
- [ ] No barrel/path-alias conventions introduced.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P01 — Monorepo scaffold
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual test/lint/typecheck output (incl. the `--dry-run` graph)
**EXCERPTS:** full code of payment/money-handling logic, auth/authz checks, and API contracts only — nothing else (likely "none")
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
