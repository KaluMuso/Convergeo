> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 4 runs 6 pebbles in parallel — **touch ONLY your files below**. You are the sole `services/api` owner this wave.

# M04-P02 — API auth dependency & role guards

## 1. Context

**Wave 4 (parallel ×6).** Grounded against as-built `master`:

- `services/api/app/` has: `settings.py` (pydantic-settings, has `supabase_url`/`supabase_service_role_key`/`supabase_anon_key` + `cloudinary_*`), `errors.py` (`AppError`, envelope `{"error":{code,message,details,request_id}}`), `supabase_client.py` (**`SupabaseServiceClient` + `get_supabase_service_client()` `@lru_cache` — the ONE service-role module**), `main.py` (router auto-discovery), `routers/{health,media}.py`, `deps.py`.
- **⚠ `services/api/app/media/authz.py` already contains a full JWKS-verify path** (`_jwks_client`, `_verify_supabase_jwt`, `require_vendor_scope`, `VendorScope`) that M05-P10 wrote as a seam and **explicitly TODO-flagged for you to consolidate**. You OWN and refactor it to delegate to the shared dependency you build here (kill the duplication).
- `0002_identity_vendors.sql`: roles live in `public.user_roles(user_id, role)`; helper `public.has_role(text)`. Verify tokens against Supabase JWKS at `{supabase_url}/auth/v1/.well-known/jwks.json`.
- Test harness: pytest + `fastapi.testclient.TestClient`; `conftest.py` clears `get_supabase_service_client` cache. `ruff` + `mypy --strict`.
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P02.

## 2. Objective & scope

Shared FastAPI auth: verified-JWT `CurrentUser`, `require_role(...)`, a per-request user-token Supabase client, a service-role import lint-guard; consolidate media's duplicate verifier onto it.
**Non-goals:** no frontend (M04-P03), no rate limiting (M04-P07), no new endpoints (dependencies + consolidation only).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/core/__init__.py` · `services/api/app/core/auth.py` (JWKS verify, `CurrentUser`, `get_current_user`, `require_role(*roles)`) · `services/api/app/core/supabase.py` (**per-request USER-token client** — takes the caller's bearer token; NOT the service-role client, which stays in `app/supabase_client.py`) · `services/api/tests/test_auth_dep.py` · `services/api/tests/test_service_role_import_guard.py`
- **Modify:** `services/api/app/media/authz.py` (refactor `require_vendor_scope` to build on `core.auth` — one JWKS-verify path; keep the `VendorScope` shape + the M04-P02-hardening TODO now partially resolved) · `services/api/app/media/__init__.py` only if an export needs it
  **Guardrail: nothing else. Do NOT move `app/supabase_client.py` (importers depend on it); do NOT touch other routers.**

## 4. Implementation spec

- **`core/auth.py`:** `verify_supabase_jwt(token, settings)` (JWKS via `PyJWKClient`, cache; `aud='authenticated'`, `iss={url}/auth/v1`, require `sub,exp`; RS256/ES256/HS256). `CurrentUser` dataclass `{id: str, roles: frozenset[str], token: str}`. `get_current_user` dependency: extract bearer → verify → **read roles from `public.user_roles` via the service-role client, cached per request** (do NOT trust role claims in the JWT). `require_role(*required)` dependency factory → 403 envelope if none of the user's DB roles match. Missing/expired/tampered/no token → **401 envelope**; **a forged `role: admin` claim in the JWT body but no DB admin row → 403** (roles come from DB, never the token).
- **`core/supabase.py`:** `get_user_client(token)` → a Supabase client initialized with the anon key + the caller's access token (RLS applies as that user). Isolated from the service-role client.
- **Service-role lint-guard (`test_service_role_import_guard.py`):** a test that greps the tree and asserts `get_supabase_service_client` / `SupabaseServiceClient` is imported ONLY from an allowlist (`app/core/`, `app/supabase_client.py` itself, and any pre-existing approved module) — so service-role usage stays greppable to one place.
- **media consolidation:** `media/authz.py`'s `require_vendor_scope` now calls `core.auth.get_current_user` then derives `VendorScope` — deleting the duplicate `_jwks_client`/`_verify_supabase_jwt` there. Existing `test_media.py` must still pass (its dependency-override still works — keep `require_vendor_scope` injectable).

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. Roles cached per-request (one DB read per request, not per dependency).

## 9. Security

**Role forging impossible** — roles read from `user_roles`, never from JWT claims (the headline test); expired/tampered/absent tokens → 401; service-role client confined to one module + lint-guarded; user-token client applies RLS as the caller.

## 10. Tests (RUN before reporting — `uv run pytest`, `ruff`, `mypy`)

`test_auth_dep`: valid token → CurrentUser with DB roles; **forged admin claim + no DB row → 403**; expired/tampered/missing → 401 envelope; `require_role('admin')` passes only real admins. `test_service_role_import_guard`: fails if service-role imported outside the allowlist (demonstrate by asserting current tree passes). `test_media.py` still green after the authz refactor. `uv run ruff check`, `uv run mypy`, full `uv run pytest` green.

## 11. Acceptance criteria / DoD

- [ ] `CurrentUser` + `require_role` verify via JWKS and read roles from DB; forged-claim → 403 (tested).
- [ ] Per-request user-token client provided; service-role usage greppable to one module + lint-guarded.
- [ ] `media/authz.py` consolidated onto `core.auth` (no duplicate JWKS path); `test_media.py` still green.
- [ ] ruff + mypy + pytest green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M04-P02 — API auth dependency & role guards
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste pytest/ruff/mypy output incl. forged-claim-403 + import-guard
**EXCERPTS:** full code of `core/auth.py` (`verify_supabase_jwt`, `get_current_user`, `require_role`) + the refactored `media/authz.py` (authz surfaces) — nothing else
**QUESTIONS:** (or "none")
