> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration.** Foreground blocking calls only; run `pnpm --filter vendor lint typecheck test` + the media API test before reporting.

# FIX-H — Cloudinary signed-upload `max_file_size` mismatch breaks every vendor image upload (🔴 HIGH)

## Finding (from the 2026-07-21 docs/ops audit)

`services/api/app/media/cloudinary_signing.py::build_signed_params` folds `max_file_size` into the **SHA-1 signature** (and returns it), but:

- the `/media/sign` response model `SignUploadResponse` in `services/api/app/routers/media.py` **omits** `max_file_size`, so the client never receives it; and
- every client uploader posts only `file, api_key, timestamp, signature, folder, allowed_formats` (e.g. `apps/vendor/app/[locale]/listings/_components/image-manager.tsx` ~L138-143).

Cloudinary recomputes the expected signature over the params it **actually received** (no `max_file_size`), which can never match our signature → **"Invalid Signature"** on every signed upload: listing images, vendor logo, vendor cover, and event images (all reuse `/media/sign`). It is latent only because demo images were seeded directly via the Cloudinary MCP, not through the signed-upload UI.

## Required fix (keep Cloudinary-side enforcement — recommended)

1. Add `max_file_size: int` to `SignUploadResponse` (`media.py`) and populate it in `sign_upload` from the `build_signed_params(...)` result (it is already computed there — no change needed in `cloudinary_signing.py`).
2. Add `max_file_size` to the signed-params **type** and the upload **FormData** in all four client uploaders:
   - `apps/vendor/app/[locale]/listings/_components/image-manager.tsx`
   - `apps/vendor/app/[locale]/profile/_components/logo-upload.tsx`
   - `apps/vendor/app/[locale]/profile/_components/cover-upload.tsx`
   - `apps/vendor/app/[locale]/events/_components/image-picker.tsx`
   Append `formData.append("max_file_size", String(signed.max_file_size))`.
3. **Invariant to enforce and comment:** the params SENT to Cloudinary must be EXACTLY the params SIGNED. Audit `public_id` too — if it is ever signed it must also be returned by `SignUploadResponse` and sent by the client; today it is not requested, so confirm and keep them consistent.

_Alternative (only if the 5-file change is unwanted): drop `max_file_size` from both dicts in `build_signed_params` — a 1-file fix that unbreaks uploads but loses Cloudinary's byte-cap enforcement (server still pre-checks the client-supplied `file_size_bytes`). Pick one; do not do both._

## Files (ONLY)

- Modify `services/api/app/routers/media.py`
- Modify the four vendor uploader components listed above
- Extend `apps/vendor/app/[locale]/listings/_components/image-manager.test.tsx` and the media-sign API test (`services/api/tests/test_media*.py`)
- **Do NOT touch** `cloudinary_signing.py` (already correct), other routers, or `db.ts`.

## Tests (RUN)

- API test: `/media/sign` response includes `max_file_size` equal to the signed value.
- Vendor unit test: the upload FormData includes `max_file_size`.
- **Manual live verify (record in PR):** one real signed upload against the `convergeo` Cloudinary cloud returns HTTP 200 (not "Invalid Signature").

## Report

STATUS / FILES / DEVIATIONS (which approach: return+send vs drop-from-signing) / TESTS (paste the API assertion + the live-upload 200) / EXCERPT the response model + one client FormData block / QUESTIONS.
