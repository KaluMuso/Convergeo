> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 3 runs 5 pebbles in parallel — **touch ONLY your files below**. Do NOT touch `packages/ui/**` (the frontend media kit is already merged — see below), `supabase/**`, or any app.

# M05-P10 — Media backend (Cloudinary signing endpoint)

## 1. Context

**Wave 3 (parallel ×5).** Grounded against as-built `master`:

- ⚠ **The frontend URL builder ALREADY EXISTS** — M02-P08 merged `packages/ui/src/media/cloudinary-url.ts` exporting `cldUrl`, `cldSrcSet`, `cldLqipUrl`, `sanitizePublicId` (consumed by `cloudinary-image.tsx`). The pebble spec's planned `packages/ui/src/media/url.ts` would **duplicate** it — **DO NOT create it, do not touch `packages/ui`**. That file already IS the D26 CDN-swap seam; you only document it.
- `services/api` uses **router auto-discovery** (`app/main.py` → `discover_routers()` via `pkgutil.iter_modules` over `app/routers/`, picking up any module exposing `router: APIRouter`). **Add a router module — never edit `main.py`.** App-factory + `app/settings.py` (pydantic-settings) + `app/errors.py` (envelope `{"error":{code,message,details,request_id}}`) + `app/supabase_client.py` (service-role) exist. Test harness: pytest + `fastapi.testclient.TestClient` in `services/api/tests/` (`conftest.py` clears `get_supabase_service_client` cache).
- Env: **`CLOUDINARY_URL`** is the single declared Cloudinary var (format `cloudinary://<api_key>:<api_secret>@<cloud_name>`) — parse api_key/api_secret/cloud_name from it. It's in `packages/config` env schema but NOT yet in `services/api/app/settings.py` — you add it there.
- ⚠ **No API auth dependency exists yet** (M04-P02 lands in Wave 4). So real per-vendor JWT authz can't be finished here — gate behind a documented seam (below).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P10.

## 2. Objective & scope

A signed-direct-to-Cloudinary upload-params endpoint (no bytes through the API), per-vendor folder scoping, size/type limits, + docs. The single CDN-swap seam stays the existing frontend `cloudinary-url.ts`.
**Non-goals:** no frontend changes, no actual upload proxying, no vendor UI (M12-P05/M12-P07), no real JWT verification (seam only — M04-P02).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/media.py` (the `router`) · `services/api/app/media/__init__.py` + `services/api/app/media/cloudinary_signing.py` (pure signing logic) · `services/api/app/media/authz.py` (the documented vendor-scope seam) · `services/api/tests/test_media.py`
- **Modify:** `services/api/app/settings.py` (add `cloudinary_url` field, parsed helpers) — you solely own services/api this wave
- **Create:** `docs/ops/media-pipeline.md`
  **Guardrail: nothing else.**

## 4. Implementation spec

- **`cloudinary_signing.py` (pure, unit-testable):** `parse_cloudinary_url(url) -> (cloud_name, api_key, api_secret)`; `build_signed_params(*, folder, public_id?, timestamp, api_secret, allowed_formats, max_bytes) -> dict` computing Cloudinary's **SHA-1 signature** over the sorted param string per Cloudinary's spec (params joined `k=v&…` + api_secret, hex digest). Include `folder`, `timestamp`, `allowed_formats` (`jpg,png,webp,avif`), and a size limit via `context`/eager or documented client-enforced `max_bytes`. Never returns api_secret.
- **`authz.py` (the seam):** `require_vendor_scope()` FastAPI dependency returning a `VendorScope(vendor_id)` — for NOW it reads + verifies the Supabase JWT from the `Authorization: Bearer` header IF present (use `SUPABASE_*` settings; verify signature via the project JWKS or the shared JWT secret) and extracts the caller; folder scoping derives `listings/{vendor_id}/…`. **Clearly-commented TODO**: full role/vendor-ownership verification hardens in **M04-P02**; keep the dependency injectable so `test_media.py` overrides it with a fixed vendor_id. Reject when no valid caller.
- **`media.py`:** `router = APIRouter(prefix="/media", tags=["media"])`; `POST /media/sign` (body: `resource_kind` e.g. `listing`, optional `public_id`) → depends on `require_vendor_scope` → returns `{cloud_name, api_key, timestamp, signature, folder, allowed_formats}`. **Folder is server-derived** `listings/{scope.vendor_id}/…` — the client cannot choose another vendor's folder. Oversized/wrong-kind requests rejected with the error envelope. Uses `app.settings` for `CLOUDINARY_URL`. No file bytes touch the API.
- **`docs/ops/media-pipeline.md`:** the signed-direct-upload flow (client asks `/media/sign` → uploads straight to Cloudinary with the signed params), folder convention `listings/{vendor_id}/…`, `f_auto,q_auto` delivery, size/type limits, and the **D26 seam note**: the ONLY place a CDN swap happens is `packages/ui/src/media/cloudinary-url.ts` (frontend delivery URLs) — document, don't duplicate.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A (backend). Signed uploads keep bytes off the API (perf/cost). Eager `f_auto,q_auto` documented.

## 9. Security

api_secret parsed from env, **never returned or logged**; signature computed server-side only; **vendor A cannot sign into vendor B's folder** (folder derived from the authenticated scope, not client input) — the headline test; unsigned/oversized/wrong-type rejected; the authz seam fails closed (no valid caller → 401/403 via envelope).

## 10. Tests (RUN before reporting — `uv run pytest`)

- `cloudinary_signing`: `parse_cloudinary_url` golden; signature golden vs a known Cloudinary example vector; api_secret never in output.
- `/media/sign`: with injected vendor scope A → folder is `listings/A/…`; **a request attempting vendor B's folder still gets A's folder** (folder is server-derived, client cannot override) — prove B-injection impossible; missing/invalid auth → 401/403 envelope; wrong resource_kind/oversize → 4xx envelope.
- `uv run ruff check`, `uv run mypy`, `uv run pytest` green; `pnpm typecheck` (config env unaffected).

## 11. Acceptance criteria / DoD

- [ ] `/media/sign` returns valid signed params; api_secret never exposed.
- [ ] Folder server-derived per authenticated vendor; cross-vendor folder impossible (tested).
- [ ] Router auto-discovered (main.py untouched); signing logic pure + golden-tested.
- [ ] No `packages/ui` / `url.ts` duplication; D26 seam documented at the existing `cloudinary-url.ts`.
- [ ] Auth seam clearly TODO-flagged for M04-P02; api green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M05-P10 — Media backend (Cloudinary signing endpoint)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste pytest/ruff/mypy output incl. the cross-vendor-folder test
**EXCERPTS:** full code of `cloudinary_signing.py` + the `/media/sign` handler + `authz.py` seam (signing/authz surfaces) — nothing else
**QUESTIONS:** (or "none")
