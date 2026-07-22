# Vendor upload flow — end-to-end verification (KYC → listing → image upload)

**Date:** 2026-07-22 · **Primary goal:** confirm **#416** (Cloudinary `max_file_size` signing fix) works against the real `convergeo` cloud — a signed vendor upload must return **HTTP 200**, not `"Invalid Signature"`. Secondary: exercise the vendor onboarding path (KYC → verified → create listing → attach image → renders on customer PDP).

No Lenco / no money involved. Cloudinary is already configured (`CLOUDINARY_URL` on the API, `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=convergeo` on Vercel).

---

## 0. Preconditions

- API `GET /healthz` = 200. Vendor app reachable (`vendor.vergeo5.com` or the Vercel URL).
- A throwaway vendor account (phone-OTP) and an admin login (Cloudflare Access) to approve KYC.
- Optional: run the API tip that includes #416 — confirm `services/api/app/routers/media.py::SignUploadResponse` has `max_file_size` on the deployed image (this is the fix; if the prod API is behind, promote it first).

## 1. KYC → verified vendor

1. Vendor onboarding: `POST /kyc/bootstrap` → `POST /kyc/submit` (business name, archetype, PACRA/TPIN, KYC docs).
   - KYC docs upload via `POST /kyc-doc/sign` → **Supabase Storage** (private `kyc-docs` bucket) — a *different* signed path than listing images. Confirm the doc lands in the private bucket and is **not** publicly readable.
2. Admin app → KYC queue → **approve**. (`admin.vergeo5.com`, Access-gated.)
3. `GET /kyc/status` → `verified`, and `archetype` + `business_name` returned.

**Checkpoint:** vendor is `verified`; `kyc_records` row exists (this also moves S5/KYC evidence off zero).

## 2. Create a listing

1. `GET /vendor/listings/categories` → pick a category; `GET /vendor/listings/canonical/{product_id}` to attach to a canonical product (or create a vendor listing per the app flow).
2. `POST /vendor/listings` → `listing_id` (price in **integer ngwee**, ZMW).

**Checkpoint:** listing created, owned by this vendor (`vendors.owner_user_id`).

## 3. Image upload — **the #416 verification**

1. `POST /media/sign` with `{ "resource_kind": "listing", "file_size_bytes": <bytes> }` (vendor JWT).
   **Assert the response now includes `max_file_size`** alongside `cloud_name, api_key, timestamp, signature, folder, allowed_formats`. Folder must be server-derived `listings/{vendor_id}` (any `folder` you send is ignored).
2. Upload the file directly to Cloudinary with **exactly** the signed params:
   ```bash
   curl -sS -X POST "https://api.cloudinary.com/v1_1/convergeo/image/upload" \
     -F "file=@sample.jpg" \
     -F "api_key=$API_KEY" \
     -F "timestamp=$TS" \
     -F "signature=$SIG" \
     -F "folder=listings/$VENDOR_ID" \
     -F "allowed_formats=jpg,png,webp,avif" \
     -F "max_file_size=$MAX_FILE_SIZE"
   ```
   **PASS = HTTP 200 with a `public_id`/`secure_url`.** A `401` / `{"error":{"message":"Invalid Signature"}}` means the fix isn't deployed (or a param sent ≠ param signed) — that is the exact regression #416 closes.
   - Do the same through the **vendor UI** (listing image manager) — the browser posts the same FormData via `uploadToCloudinaryWithProgress`; logo/cover/event pickers reuse it, so verify **one** of those too.
3. `POST /vendor/listings/{listing_id}/images` with the returned `public_id` → attaches the image (position, cover, ≤8 cap enforced server-side).

**Assert:**
- Cloudinary has the asset under `listings/{vendor_id}/…` (MCP `search-assets` or dashboard).
- `listing_images` row exists for the listing.
- Uploading a **9th** image is rejected 4xx (`MAX_IMAGES_PER_LISTING=8`).

## 4. Renders on the customer surface

Open the customer PDP for the listing — the image should render via `cldUrl` (`f_auto,q_auto,w_…`) with a responsive `srcset` (360/720/1080) and an LQIP blur placeholder. Confirm no broken image and the bytes are WebP/AVIF where supported.

## 5. Evidence to capture

- `POST /media/sign` response showing `max_file_size` present.
- The Cloudinary upload **200** (redact api_key/signature) — this is the #416 proof.
- `listing_images` row id + Cloudinary `public_id`.
- Screenshot of the image on the customer PDP.

## 6. If the upload still 401s

- Confirm the **deployed** API is at a tip that includes #416 (`SignUploadResponse.max_file_size`). If the prod API image predates it, redeploy the API to master first.
- Confirm the client sends `max_file_size` (the four uploaders were patched in #416). A param signed-but-not-sent (or sent-but-not-signed) always yields `Invalid Signature`.
- As a fallback only, the minimal variant (drop `max_file_size` from the signed set in `cloudinary_signing.py`) also unbreaks uploads but loses Cloudinary's byte-cap enforcement.
