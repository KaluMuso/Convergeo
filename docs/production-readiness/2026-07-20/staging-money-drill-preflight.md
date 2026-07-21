# Staging money-drill preflight (2026-07-21)

Companion to `docs/ops/staging-money-drill.md`. Evidence from this agent session;
does **not** claim S1–S6 PASS.

## Live fingerprint

| Check                                 | Result                                               |
| ------------------------------------- | ---------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz` | **200** `{"status":"ok"}`                            |
| `GET https://api.vergeo5.com/readyz`  | **200** `{"status":"ok"}`                            |
| Customer `/en/health`                 | **200**                                              |
| Supabase tip                          | **`0066_user_wishlist_recently_viewed`** applied     |
| Money rows                            | `orders` / `payments` historically empty (pre-drill) |
| `public_launch`                       | remains false (do not flip)                          |

## Catalog empty → drill fixtures

Public catalog returned `total: 0` while DB had **134** active listings — all carried
`listing_images.cloudinary_public_id LIKE 'demo/%'`, so FD-04 / VC-P06 exclusion
hid every row.

**Applied** `scripts/ops/staging-money-drill-fixtures.sql` (via Supabase MCP) to
rewrite five COD-eligible retail listings to `staging-drill/…` public_ids.

| Listing ID                             | Product slug            | Price (ngwee) |
| -------------------------------------- | ----------------------- | ------------- |
| `b904645c-ed91-1329-72e3-43d7868855fe` | `tea-coffee-standard`   | 2897          |
| `388660b1-40c5-d004-7bde-f9c532686c67` | `footwear-premium`      | 4212          |
| `7cbffa47-c958-410b-ae32-e341d6b52fa3` | `flour-baking-standard` | 4632          |
| `cef8e01d-4184-5e19-9fcf-732d7166a39b` | `beverages-standard`    | 4901          |
| `0b33171a-468c-ecec-71c1-61f96ca48076` | `cooking-oil-5l`        | 5562          |

**Post-apply probe:** `GET /catalog/listings?limit=5` → `total: 5` with the rows above.
`GET /products/tea-coffee-standard` → 1 listing. Search for `tea` returns the listing
(still `degraded: true` — embeddings cron / OpenRouter; keyword lane OK).

**Image note:** Cloudinary assets may 404 until renamed/copied to `staging-drill/…`
(Cloudinary MCP needs founder auth). Checkout does not require images.

## Still blocking full S1–S3

1. **F9b** — Lenco sandbox token / account / public key on API host (agent has no secrets).
2. Authenticated buyer OTP session for cart → checkout UI path.
3. MoMo sandbox push + webhook settle evidence.
4. Optional: re-auth Cloudinary MCP and copy `demo/categories/*` → `staging-drill/categories/*`.

## Next operator steps

1. Confirm `LENCO_*` sandbox env on Hetzner API container (not prod keys).
2. Sign in as staging buyer → add `tea-coffee-standard` → cart revalidate → COD ≤K500
   and/or MoMo sandbox per `docs/ops/staging-money-drill.md`.
3. Attach order id + `pay-*` / `ord-*` references to this folder when done.

## n8n non-money activation (2026-07-21)

Manual ticks against healthy API, then publish (money workflows left **unpublished**):

| Workflow               | ID                 | Manual exec | Result                                              | Published          |
| ---------------------- | ------------------ | ----------- | --------------------------------------------------- | ------------------ |
| Notification dispatch  | `sevKtX1AmimQCWsG` | `12353`     | success `{processed:0}`                             | **yes**            |
| Embeddings cron        | `oqjfSdMXClfsf3qd` | `12355`     | success `{processed:0,dead:0}`                      | **yes**            |
| Reservation sweeper    | `F25zEWiPoIveARys` | `12354`     | **error** API 500 on `/internal/stock-sweeper/tick` | **no**             |
| Payment reconciliation | `C1MpTNjrfLACMG3f` | —           | money-moving                                        | **no** (await F9b) |

Credentials bound via MCP `setNodeCredential` (Dispatch + Embeddings + Stock Sweeper tokens present).
