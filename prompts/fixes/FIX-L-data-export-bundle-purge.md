> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **Migration only if you add a config knob** (prefer env/const). Run the FULL `uv run pytest` for the new tests before reporting.

# FIX-L — Auto-purge DPA data-export bundles from Storage (🟠 MED, Zambia DPA)

> **Groundwork verified 2026-07-22.** The **easy parts:** the internal tick registers like the
> others — add `"POST /internal/privacy/export-purge-tick": INTERNAL_CRON` to
> `services/api/app/core/ratelimit_policies.py`; authz is **auto-classified** by the `/internal/`
> prefix (`test_authz_matrix.py:209`), so no manual authz row is needed. The **risky core:** there
> is **no existing storage `.list()`/`.remove()` usage anywhere** in `services/api` (the code only
> `.upload()`s / signs URLs) — so the list-old-objects + delete logic is novel and **MUST be
> validated against real Supabase Storage** (the exact `.list()` pagination/recursion + `.remove()`
> shapes are version-dependent). Consider querying `storage.objects` (service-role) for
> `bucket_id='private-artifacts' AND name LIKE 'data-exports/%' AND created_at < now()-TTL`, then
> `.remove()` those paths via the Storage API. Inject the list+remove callables so the TTL logic is
> unit-tested with fakes, and gate the real path on a live smoke check.

## Finding (from the 2026-07-22 docs/ops overview)

`services/api/app/routers/privacy.py` uploads each account-data-export bundle to
`private-artifacts/data-exports/{user_id}/{export_id}.json` and hands the user a 15-minute
signed URL. But the **object itself is never deleted** — export bundles (which contain the
user's personal data) accumulate in Storage indefinitely. `docs/ops/data-retention.md` flags
this: "object auto-purge **not yet configured** (no Storage lifecycle rule)". Supabase Storage
has no native TTL, so a scheduled purge is required — mirror the existing analytics-retention
sweep (`/internal/analytics/retention-tick` + `infra/n8n/analytics-retention.json`).

## Required fix

1. **Purge service** — a service that lists objects under the `data-exports` prefix in the
   `private-artifacts` bucket (service-role) and **deletes those older than a TTL**
   (default e.g. 24h — export bundles are transient portability artefacts; make it a const/env
   `DATA_EXPORT_TTL_HOURS`). Scope strictly to `data-exports/` in `private-artifacts` — never
   another bucket/prefix. Idempotent.
2. **Internal endpoint** — `POST /internal/privacy/export-purge-tick`, guarded by an
   `X-Internal-Token` dependency (new `INTERNAL_PRIVACY_TOKEN`, mirroring
   `internal_analytics.py`; add its dev-default + the ratelimit/authz-matrix entry so the
   startup coverage assert passes). Returns `{deleted: n}`.
3. **n8n workflow** — `infra/n8n/export-purge.json`, daily schedule (set `settings.timezone:"UTC"`),
   POSTing the tick with the Header-Auth credential. Add its row to `docs/ops/n8n-workflows.md`
   (the registry test now checks the endpoint segment is documented). Bind via `setNodeCredential`
   at deploy, like the other internal ticks.
4. Update `docs/ops/data-retention.md`: the export bundles now auto-purge on the tick (drop the
   "not yet configured" ⚠).

## Files (ONLY)

- Create `services/api/app/services/privacy/export_purge.py` (+ `__init__.py` if needed)
- Create `services/api/app/routers/internal_privacy.py`
- Create `infra/n8n/export-purge.json`
- Modify `docs/ops/n8n-workflows.md` (registry row) + `docs/ops/data-retention.md`
- Add ratelimit/authz-matrix rows for the new route; add `services/api/tests/test_export_purge.py`
- **Do NOT** touch `privacy.py`'s export creation, `db.ts`, or other routers.

## Tests (RUN)

- Bundles older than the TTL are deleted; newer ones kept; a second run is a no-op (idempotent).
- The tick 401s without the token; the purge scopes to `data-exports/` only (a fixture object in
  another prefix/bucket is never deleted).
- **Full `uv run pytest`** + `ruff` + `mypy`. Startup coverage assert (ratelimit/authz) still passes.

## Report

STATUS / FILES / DEVIATIONS (TTL value; token reused vs new) / TESTS (paste purge + scope-guard results) / EXCERPT the delete-scope guard / QUESTIONS.
