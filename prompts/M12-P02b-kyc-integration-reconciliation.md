> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. **Single-pebble PR** — you own every file listed. **Do NOT merge past a red required check** — the whole point of this pebble is that real CI (now restored) validates the storage/`config.toml` change that cannot be checked locally without Docker. Safe to run in parallel with Wave 7 (disjoint files).

# M12-P02b — KYC private-doc storage & upload endpoint

## 1. Context — the contract half is already done

The Wave-6 onboarding↔KYC **API-contract** mismatch has **already been reconciled on `master`** (a direct convergence commit): `apps/vendor/app/[locale]/onboarding/_lib/kyc-client.ts` now calls the real `GET /kyc/status`, `POST /kyc/submit`, `POST /kyc/resubmit` with the correct body (`{tier, doc_storage_paths[], momo_phone, momo_operator, legal_name}`); a **`legal_name`** field is collected in `kyc-docs-step.tsx`; the draft is localStorage-only (no dead server-draft call); and `types.ts` already sets **`PRIVATE_KYC_BUCKET = "kyc-docs"`**. **Do NOT touch any of those files.**

**What's left — the storage half (this pebble):** KYC doc uploads still fail because there is **no private bucket and no signed-upload endpoint**. Grounded against as-built `master`:

- `supabase/config.toml [storage]` has **all buckets commented out** — no bucket exists.
- `services/api/app/routers/media.py` `POST /media/sign` is **Cloudinary-only, hard-locked to `Literal["listing"]`** — wrong system for a Supabase-Storage private upload.
- The onboarding client (`_lib/storage.ts`) calls `POST /media/sign {resource_kind:'kyc_doc', …}` and expects `{bucket:'kyc-docs', path, token, signed_url}` + asserts the path is under `kyc/`. You repoint it to the new endpoint.
- API routers auto-discover (never edit `main.py`); `require_vendor_scope` (from `app.media.authz`) gives `scope.vendor_id`; `get_supabase_client` (`app.deps`) gives the service-role client; storage3's `create_signed_upload_url(path)` exists on the pinned supabase-py.

## 2. Objective & scope

A private `kyc-docs` Storage bucket + a vendor-scoped signed-upload endpoint, and the onboarding storage client repointed to it — so NRC/selfie uploads work end-to-end.
**Non-goals:** no changes to the KYC API contract / onboarding flow (already done), no admin KYC-approval UI (M13-P02), no read/download endpoint yet (M13-P02 signs downloads).

## 3. Files (create/modify ONLY these)

- Modify `supabase/config.toml`: add a **private** bucket —
  ```toml
  [storage.buckets.kyc-docs]
  public = false
  file_size_limit = "10MiB"
  allowed_mime_types = ["image/jpeg", "image/png", "image/webp"]
  ```
  **⚠ VERIFY `supabase db start` still comes up in CI** (the `db` + `rls` jobs run it — currently green). Do not add `objects_path` unless you also add the seed dir. If the CLI rejects the block, adjust until `db start` is green — this is the untestable-locally piece, so lean on CI. **Do NOT admin-override a red `db`/`rls` job.**
- Create `services/api/app/routers/kyc_media.py` (auto-discovered): `POST /media/kyc-doc/sign`, deps `require_vendor_scope` (vendor_id) + `get_supabase_client` (service-role). Body `{doc_type: 'nrc'|'selfie', file_size_bytes: int}` (reject > 10 MiB → `file_too_large`). Path `f"kyc/{scope.vendor_id}/{doc_type}-{int(time.time())}"`. Call `service_client.client.storage.from_("kyc-docs").create_signed_upload_url(path)`; return `{bucket: "kyc-docs", path, token, signed_url}` — parse storage3's return keys **defensively** (`signed_url`/`signedUrl`, `token`, `path`). Envelope errors on storage failure (`503`/`configuration_error`).
- Create `services/api/tests/test_kyc_media.py`: mock the storage client (override `get_supabase_client` + `require_vendor_scope`); assert the path is `kyc/{vendor_id}/{doc_type}-…`, the size cap returns 400, the response has `bucket:'kyc-docs'` + `signed_url`, and a non-vendor caller is rejected.
- Modify `apps/vendor/app/[locale]/onboarding/_lib/storage.ts`: change the request path from `/media/sign` to **`/media/kyc-doc/sign`**; keep the `{resource_kind:'kyc_doc', doc_type, file_size_bytes}` body (or trim to `{doc_type, file_size_bytes}` to match the endpoint — match the endpoint you build); keep the `PRIVATE_KYC_BUCKET` + `kyc/` path assertions (they already expect `kyc-docs`).
  **Guardrail: nothing else. Do NOT touch `kyc-client.ts`, `types.ts`, `persistence.ts`, `onboarding-flow.tsx`, `kyc-docs-step.tsx`, `vendor.json` (contract half — already landed), `media.py`, `kyc.py`, migrations, or `main.py`.**

## 4. Security

The `kyc-docs` bucket is **private** → Supabase enables RLS on `storage.objects` with no client policy for it, so only the service-role backend (via signed URLs) can read/write. The endpoint is **vendor-scoped** (path pinned to `kyc/{vendor_id}/…` — a vendor cannot sign into another's folder). No public policy; PII (NRC/selfie) never logged.

## 5. Tests (RUN before reporting)

- Backend: `uv run pytest` (incl. `test_kyc_media.py`), `ruff`, `mypy`.
- Frontend: `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.
- **CI must be fully green — especially `db` + `rls`** (they run `supabase db start`, now creating the `kyc-docs` bucket). If red on the bucket block, fix `config.toml` until green. **No admin-override.**

## 6. Acceptance criteria / DoD

- [ ] `POST /media/kyc-doc/sign` returns a Supabase-Storage private signed upload scoped to `kyc/{vendor_id}/…`; size cap enforced; vendor-scoped.
- [ ] `kyc-docs` bucket private in `config.toml`; `db`+`rls` CI jobs green with it (no override).
- [ ] `storage.ts` calls the new endpoint; vendor build/test green.

## 7. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M12-P02b — KYC private-doc storage & upload endpoint
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste backend pytest (incl. kyc_media) + vendor build + the **CI job conclusions** (db + rls green with the bucket)
**EXCERPTS:** the `/media/kyc-doc/sign` handler — nothing else
**QUESTIONS:** (or "none")
