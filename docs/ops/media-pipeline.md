# Media pipeline

Vergeo5 listing images use **signed direct-to-Cloudinary uploads**: the API never receives file bytes. Vendors obtain short-lived upload parameters from the API, then POST the file straight to Cloudinary.

## Flow

```mermaid
sequenceDiagram
    participant Vendor as Vendor app
    participant API as Vergeo5 API
    participant CDN as Cloudinary

    Vendor->>API: POST /media/sign (Bearer JWT, resource_kind, optional public_id)
    API->>API: Verify JWT, derive listings/{vendor_id}/ folder
    API->>API: SHA-1 signature (server-side only)
    API-->>Vendor: cloud_name, api_key, timestamp, signature, folder, allowed_formats
    Vendor->>CDN: POST /v1_1/{cloud_name}/image/upload (signed params + file)
    CDN-->>Vendor: public_id, secure_url, ...
```

1. Authenticated vendor calls `POST /media/sign` with `resource_kind` (currently `listing`), optional `public_id`, and optional `file_size_bytes` for pre-upload size checks.
2. API verifies the Supabase access token, derives the upload folder from the authenticated vendor scope, and returns signed parameters.
3. Client uploads directly to `https://api.cloudinary.com/v1_1/{cloud_name}/image/upload` with `api_key`, `timestamp`, `signature`, `folder`, `allowed_formats`, and the file.

## Folder convention

Upload folders are **server-derived** and scoped per vendor:

```text
listings/{vendor_id}/...
```

Clients cannot choose another vendor's folder. Any `folder` field sent in the sign request is ignored; the API always signs the folder for the authenticated vendor.

`public_id`, when provided, is sanitized to a single path segment (no `../` or slashes).

## Limits

| Constraint             | Value                                        |
| ---------------------- | -------------------------------------------- |
| Allowed formats        | `jpg`, `png`, `webp`, `avif`                 |
| Max listing image size | 10 MiB (`10_485_760` bytes)                  |
| Images per listing     | ≤ 8 (enforced **client and server** — `listing_images.py` `MAX_IMAGES_PER_LISTING`, hard 4xx) |
| Signature validity     | 1 hour from `timestamp` (Cloudinary default) |

Oversized `file_size_bytes` in the sign request is rejected before a signature is issued.

> ⚠ **Known signing bug — fix pending.** `build_signed_params` (`cloudinary_signing.py`) folds `max_file_size` into the SHA-1 signature, but `/media/sign`'s `SignUploadResponse` omits it **and** no client sends it. Cloudinary recomputes the digest over the params it actually *received* (no `max_file_size`), so it never matches our signature → **"Invalid Signature"** on every signed upload (listing, logo, cover, event). Fix: either return **and** send `max_file_size`, or drop it from the signed set — then verify against a real Cloudinary upload. Latent so far only because demo images were seeded directly (no real vendor has used the signed-upload UI).

## Delivery (`f_auto`, `q_auto`)

After upload, customer-facing apps render images through the shared UI helpers in `packages/ui/src/media/cloudinary-url.ts`:

- `cldUrl` — `f_auto,q_auto,w_{width}` delivery URLs
- `cldSrcSet` — responsive widths 360 / 720 / 1080
- `cldLqipUrl` — tiny blurred placeholder

Configure `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` in frontend environments for delivery URLs.

## D26 CDN swap seam

**The only place a CDN provider swap should happen is `packages/ui/src/media/cloudinary-url.ts`.**

Do not duplicate URL builders in the API or apps. Backend signing uses Cloudinary upload credentials from `CLOUDINARY_URL`; frontend delivery URLs stay centralized in the UI package so a future CDN migration touches one module.

## Environment

| Variable                            | Service      | Format                                             |
| ----------------------------------- | ------------ | -------------------------------------------------- |
| `CLOUDINARY_URL`                    | API          | `cloudinary://<api_key>:<api_secret>@<cloud_name>` |
| `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` | Next.js apps | Cloud name for read-only delivery URLs             |

`api_secret` is parsed server-side only and must never be returned to clients or logged.

## Auth seam

`services/api/app/media/authz.py` verifies the Supabase JWT and resolves the vendor scope from **DB ownership** (`vendors.owner_user_id`) — never from token claims, so a caller cannot set `user_metadata.vendor_id` to another vendor's id. This closed the former M04-P02 TODO; the earlier "vendor_id from claims" behavior is superseded.
