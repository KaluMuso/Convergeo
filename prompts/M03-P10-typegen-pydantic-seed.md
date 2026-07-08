> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 5 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FREEZE ACTIVE** — no schema migrations; the catalog seed goes in `supabase/seed.sql` (not a numbered migration). **You are the authoritative `db.ts` regenerator this wave — MERGE LAST** (see db.ts rule).

# M03-P10 — Type generation, Pydantic base & catalog seed

## 1. Context

**Wave 5 (parallel ×6).** Grounded against as-built `master`:

- `packages/types/src/db.ts` is **hand-maintained in-cloud** (no Docker in Cursor cloud VMs) and currently carries the union of tables through `0009` + trust/money/search. **The CI `db` job now works again** (its missing auth-hook secrets were fixed) — it runs `supabase db start` → `db reset` → `scripts/gen-types.sh` → `git diff --exit-code packages/types/src/db.ts`. So **your committed `db.ts` MUST match what `scripts/gen-types.sh` produces**, or CI fails. If you cannot run Docker, hand-align `db.ts` to the exact generator output shape (the script uses `supabase gen types typescript`).
- **M04-P07 (same wave) adds migration `0011_rate_counters.sql`** → a `rate_counters` table that must appear in `db.ts`. You regenerate from ALL migrations incl. `0011`; **you merge LAST** so your regen is authoritative. If `0011` is not yet merged when you open your PR, note it and include `rate_counters` from M04-P07's committed migration.
- **`0010` is already `0010_profile_bootstrap.sql`** — the catalog seed is **`supabase/seed.sql`** (applied by `db reset` without `--no-seed`), NOT a numbered migration. (The spec's "0010_seed_catalog" name is stale.)
- `services/api/app/` has `settings.py`, `errors.py`, `core/` (auth). **There is no `app/schemas/` yet — you create it.** `NgweeInt` and reference codecs (`ord-*`/`pay-*`/`rfd-*`, charset `[-._A-Za-z0-9]`) are money/idempotency-critical.
  Spec: `docs/plan/02-pebbles/M03-data-core.md` §M03-P10.

## 2. Objective & scope

Authoritative generated `db.ts`; shared API DTO types; a strict Pydantic base (NgweeInt + reference codecs); the category-tree + canonical-product-stub seed; and a whole-schema ERD.
**Non-goals:** no schema changes (freeze), no RLS matrix (M03-P09), no endpoints (base classes only), no app UI.

## 3. Files (create/modify ONLY these)

- **Modify/own:** `packages/types/src/db.ts` (authoritative regen — merge last)
- **Create:** `packages/types/src/api/index.ts` (+ DTO modules as needed) · `services/api/app/schemas/__init__.py` · `services/api/app/schemas/base.py` · `services/api/tests/test_schemas_base.py` · `supabase/seed.sql` · `supabase/tests/seed.test.sql` · `docs/plan/erd.md`
  **Guardrail: nothing else. Do NOT add migrations, do NOT touch `pyproject.toml` (M04-P07 owns Python deps), do NOT edit `scripts/gen-types.sh` or `.github/**` (M01-P09).**

## 4. Implementation spec

- **`app/schemas/base.py`:** `class StrictModel(BaseModel): model_config = ConfigDict(strict=True, extra='forbid')`. `NgweeInt = Annotated[int, ...]` that **rejects floats/strings at parse** (a `float` like `10.5` must raise, not coerce) and enforces `>= 0` where appropriate. Reference codecs: validators/typed wrappers for `ord-*`, `pay-*`, `rfd-*` enforcing charset `[-._A-Za-z0-9]` and the prefix — reject bad charset/prefix. Keep it pure (no DB).
- **`packages/types/src/api/`:** hand-authored shared DTO types (request/response shapes) that both frontend and (conceptually) the API agree on — e.g. money is `number` (ngwee int) with a branded comment, reference strings typed. Small, additive; deep-import friendly (no heavy barrel).
- **`supabase/seed.sql`:** the category tree (8 departments → ~60–80 subcategories per D8) with the materialized `path` populated, **no orphans**; ~150 canonical product stubs (name, spec skeleton, category, aliases incl. Bemba/Nyanja per D25). Idempotent-friendly (stable ids / `on conflict do nothing`) so `db reset` re-seeds cleanly. Founder-reviewable: readable, commented, grouped by department.
- **`docs/plan/erd.md`:** a mermaid ERD covering **every** table + key FKs (identity→catalog→orders→money→trust→search→config→rate_counters).

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A.

## 9. Security

Seed inserts only public/demo-safe data; no secrets; NgweeInt + reference codecs are money/idempotency guards (float-money → parse error is the headline test).

## 10. Tests (RUN before reporting)

`test_schemas_base.py`: float money rejected, negative-where-forbidden rejected, valid ngwee accepted; bad reference charset/prefix rejected, valid `ord-…`/`pay-…`/`rfd-…` accepted (`uv run pytest`, `ruff`, `mypy`). `supabase/tests/seed.test.sql`: category-tree integrity (no orphan `parent_id`, `path` consistent), product-stub row count in range, aliases present. `pnpm --filter @vergeo/types typecheck`. If Docker available: `supabase db reset` (with seed) clean + `scripts/gen-types.sh` leaves `db.ts` unchanged (drift-clean); else state the drift check is deferred to CI and that `db.ts` was hand-aligned to the generator shape.

## 11. Acceptance criteria / DoD

- [ ] `db.ts` authoritative + drift-clean under `gen-types.sh` (or hand-aligned + noted); includes `rate_counters`.
- [ ] `NgweeInt` rejects floats at parse; reference codecs reject bad charset/prefix (tested).
- [ ] `supabase/seed.sql` founder-reviewable; category tree has no orphans; ERD covers every table.
- [ ] Python + types green.

## db.ts rule (you are the authority this wave)

`db.ts` is hand-maintained in-cloud with **no auto-regenerator except CI**. You own the authoritative regen and **merge LAST** in the wave. M04-P07 appends `rate_counters`; you fold it in. After your merge, CI's `db` job (now functional) is the drift gate. Report that explicitly.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P10 — Type generation, Pydantic base & catalog seed
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste strict-mode (float-money reject) + reference-codec + seed-integrity + types typecheck output
**EXCERPTS:** full `base.py` (NgweeInt + reference codecs) + the category-tree head of `seed.sql` — nothing else
**QUESTIONS:** (or "none")
