> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. **Single-pebble convergence PR** (not a parallel wave) — you own every file listed. **Do NOT merge past a red required check** — the whole point of this pebble is that real CI (now restored) validates the storage/`config.toml` change that could not be checked locally.

# M12-P02b — KYC onboarding↔backend integration reconciliation

## 1. Why this exists

Wave 6 shipped M12-P01 (onboarding UI) and M12-P02 (KYC backend) in parallel; they **do not integrate** (each tested itself in isolation, so CI was green but the flow is broken end-to-end):

1. **Endpoint/contract mismatch.** The UI (`apps/vendor/app/[locale]/onboarding/_lib/kyc-client.ts`) calls `GET /kyc/application`, `PATCH /kyc/application/draft`, `POST /kyc/application/{submit,resubmit}` — **none exist**. The backend (`services/api/app/routers/kyc.py`) actually serves:
   - `GET /kyc/status` → `KycStatusResponse{application_status, vendor_status, kyc_tier, kyc_record_id, kyc_record_status, tier, doc_storage_paths: string[], momo_name_match, reviewer_notes}`
   - `POST /kyc/submit` **body** `KycSubmitRequest{tier: 1|2|3, doc_storage_paths: string[] (min 1), momo_phone (8–20), momo_operator?: 'mtn'|'airtel'|'zamtel'|null, legal_name (2–200)}` → `KycSubmitResponse{application_status, kyc_record_id, momo_name_match}`
   - `POST /kyc/resubmit` same body; **409** unless current status is `rejected`.
     The backend `KycApplicationStatus` enum is **`draft|submitted|approved|rejected`** — there is **no `resubmit` value** (resubmit-eligible == `rejected`). The backend has **no draft-persistence endpoint** and stores **no business_name/business_category/per-doc paths** — only a flat `doc_storage_paths[]`.
2. **No private-doc signing endpoint exists.** The UI (`_lib/storage.ts`) calls `POST /media/sign {resource_kind:'kyc_doc', doc_type, file_size_bytes}` expecting `{bucket, path, token, signed_url}` (a Supabase-Storage signed upload). But `/media/sign` is **Cloudinary-only, hard-locked to `Literal["listing"]`**. And **no storage bucket is configured** (`supabase/config.toml [storage]` has all buckets commented out).
3. **Missing field:** the backend requires `legal_name` for the MoMo name-match; the onboarding UI never collects it.

## 2. Objective & scope

Make onboarding → KYC work end-to-end: a private KYC-docs Storage bucket + a signed-upload endpoint, the onboarding client aligned to the real `/kyc/status|submit|resubmit` contract, and a `legal_name` field collected for name-match.
**Non-goals:** no admin KYC-approval UI (M13-P02), no listing creation (M12-P03), no changes to caps/state-machine logic (M12-P02 backend stays as-is except the new signing endpoint).

## 3. Files (create/modify ONLY these)

- **Backend — private-doc signing:**
  - Modify `supabase/config.toml`: add a **private** bucket, e.g.
    ```toml
    [storage.buckets.kyc-docs]
    public = false
    file_size_limit = "10MiB"
    allowed_mime_types = ["image/jpeg", "image/png", "image/webp"]
    ```
    **⚠ VERIFY `supabase db start` still comes up in CI** (the `db` + `rls` jobs run it). Do not add `objects_path` unless you also add the seed dir. If the CLI rejects the bucket block, adjust until `db start` is green — this is the untestable-locally piece, so lean on CI.
  - Create `services/api/app/routers/kyc_media.py` (**auto-discovered** — do NOT edit `main.py`): `POST /media/kyc-doc/sign`, dependency `require_vendor_scope` (from `app.media.authz`) for `vendor_id` + `get_supabase_client` (service-role) for storage. Body `{doc_type: 'nrc'|'selfie', file_size_bytes: int}` (reject > 10 MiB). Path `f"kyc/{vendor_id}/{doc_type}-{int(time.time())}"`. Call `service_client.client.storage.from_("kyc-docs").create_signed_upload_url(path)` and return `{bucket: "kyc-docs", path, token, signed_url}` (handle the storage3 return keys — `signed_url`/`signedUrl`, `token`, `path` — defensively).
  - Create `services/api/tests/test_kyc_media.py` (mock the storage client; assert path is `kyc/{vendor_id}/…`, size cap enforced, vendor-scoped).
- **Frontend — contract alignment (`apps/vendor/app/[locale]/onboarding/`):**
  - `_lib/kyc-client.ts`: repoint to `GET /kyc/status`, `POST /kyc/submit`, `POST /kyc/resubmit`. `submit`/`resubmit` build the real body `{tier: 1, doc_storage_paths: [nrcPath, selfiePath].filter(Boolean), momo_phone, momo_operator: null, legal_name}`. Map `KycStatusResponse` → the UI's needs. **Drop the server `saveDraft`** (no backend draft endpoint) — draft persists via `localStorage` only (`persistence.ts` already does this). `resubmit` still guards on `application_status === 'rejected'`.
  - `_lib/storage.ts`: call `POST /media/kyc-doc/sign` (not `/media/sign`); expect `{bucket:'kyc-docs', path, token, signed_url}`.
  - `_lib/types.ts`: add `legalName` to `OnboardingDraft`; set `PRIVATE_KYC_BUCKET = "kyc-docs"`; reconcile `KycApplication`/`KycStatus` to the backend enum (`draft|submitted|approved|rejected`; treat `rejected` as resubmit-eligible).
  - `_lib/persistence.ts`: `mergeDraftWithServer` no longer maps server draft fields (backend has none) — keep local draft; add `legalName` to `DEFAULT_DRAFT` + merge.
  - `_components/kyc-docs-step.tsx`: add a **"Full name as on your NRC"** text input (`legal_name`), wired to the draft; required before continue (backend needs 2–200 chars). Add i18n keys.
  - `_components/onboarding-flow.tsx`: thread `legalName`; make `persistDraft` local-only; build the submit/resubmit payloads incl. `legal_name` + doc paths; keep the localStorage-resume behavior.
  - `_components/review-step.tsx`: show the legal name in the review summary (add label key).
  - `packages/i18n/messages/en/vendor.json`: add the `onboarding.kyc.legalNameLabel/legalNamePlaceholder/legalNameHelp` + review label keys under the existing nested `onboarding` section (no flat dotted keys; you solely own `vendor.json` here).
  - `_lib/onboarding.test.ts`: update for the new client contract (endpoints, submit body incl. `legal_name`, status enum) + the signing endpoint path.
    **Guardrail: nothing else. Do NOT touch `kyc.py` logic, other migrations, `main.py`, other apps, or `request.ts`.**

## 4. Notes / correctness

- **Business basics** (name/category) are **client-only** for now — the backend submit takes none of them (it takes `legal_name`, docs, momo, tier). Keep collecting them locally (a later pebble persists vendor profile); do not send them to `/kyc/submit`.
- **Docs** map to `doc_storage_paths = [nrcPath, selfiePath]` (filter falsy). Backend requires ≥1.
- **Security:** the `kyc-docs` bucket is **private** → Supabase enables RLS on `storage.objects` with no client policy for it, so only the service-role backend (via signed URLs) can read/write. Reads later use backend-generated signed download URLs gated by vendor/admin authz (M13-P02). Do not add a public policy.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; legal-name input labelled + validated; vendor app `noindex`; no secrets; PII (legal name, momo, docs) never logged.

## 10. Tests (RUN before reporting)

- Backend: `uv run pytest` (incl. `test_kyc_media.py` — mocked storage, size cap, vendor-scoped path), `ruff`, `mypy`.
- Frontend: `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test` (updated `onboarding.test.ts` green).
- **CI must be fully green** — especially the `db` + `rls` jobs (they run `supabase db start`, which now creates the `kyc-docs` bucket). If either goes red on the bucket block, fix `config.toml` until green. Do NOT admin-override.

## 11. Acceptance criteria / DoD

- [ ] `kyc-client.ts` hits `/kyc/status|submit|resubmit` with the exact backend body/shape; `resubmit` guarded to `rejected`.
- [ ] `legal_name` collected in the KYC step and sent on submit/resubmit; docs sent as `doc_storage_paths[]`.
- [ ] `POST /media/kyc-doc/sign` returns a Supabase-Storage private signed upload; `kyc-docs` bucket private; `storage.ts` uses it.
- [ ] Draft persists via localStorage only (no dead server-draft call). All suites + **real CI** green (no override).

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M12-P02b — KYC onboarding↔backend integration reconciliation
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste backend pytest (incl. kyc_media) + vendor build/test + the **CI job conclusions** (db + rls green with the bucket)
**EXCERPTS:** the `/media/kyc-doc/sign` handler + the aligned `kyc-client.ts` submit/resubmit — nothing else
**QUESTIONS:** (or "none")
