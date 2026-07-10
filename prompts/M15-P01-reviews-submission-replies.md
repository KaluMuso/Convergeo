> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 runs pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M15-P01 — Reviews: submission & vendor replies

## 1. Context

**Wave 15 (parallel).** Grounded against as-built `master`:

- **`reviews` table EXISTS (0007_trust_ops.sql:7):** `order_item_id uuid not null` (**UNIQUE — one review per order_item**), `rating int check 1..5`, `body text`, `photos text[]`, `vendor_reply text`, `vendor_reply_at`, `status ('published','flagged','removed')`. **No migration.** Verified-purchase = the FK link + **Delivered/Completed order state** (M09 merged) — enforce in the router.
- **Confirm-received MERGED (M09-P06):** the review prompt appears post-delivery on the order page. **Photos → public Cloudinary** (merged `CloudinaryImage`/signing seam). **Moderation via flags (M13-P04, merged):** reviews publish immediately; flagging is separate.
- **Windows:** review editable **7d**; vendor reply **one per review, editable 24h**.
- **i18n (append-rule):** PDP reviews → `catalog.json` (`catalog.reviews.*`); review prompt on order page → `orders.json` (`orders.reviewPrompt.*`); vendor reply → `vendor.json` (`vendor.reviews.*`). **M11-P03 also appends to `vendor.json` this wave — disjoint sections.**
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P01.

## 2. Objective & scope

Verified-purchase reviews: create (1–5★ + text + ≤3 public photos, **one per order_item**, editable 7d, **enforced by order_item link + delivered state**), PDP reviews section (list, photo lightbox, write entry), post-delivery review prompt, vendor reply (one per review, editable 24h). Reviews visible immediately.
**Non-goals:** no aggregation/rating rollup (M15-P02), no moderation surface (M13-P04 merged — flags separate), no schema change.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/reviews.py` (create/edit + vendor reply, verified-purchase gate, windows) · `apps/customer/app/[locale]/(shop)/p/[slug]/_components/reviews-section.tsx` (list + lightbox + write entry) · `apps/customer/app/[locale]/account/orders/[id]/_components/review-prompt.tsx` · `apps/vendor/app/[locale]/reviews/page.tsx` (reply) · `services/api/tests/test_reviews.py`
- **Modify (APPEND-RULE — disjoint sections):** `packages/i18n/messages/en/catalog.json` (`catalog.reviews.*`) · `packages/i18n/messages/en/orders.json` (`orders.reviewPrompt.*`) · `packages/i18n/messages/en/vendor.json` (`vendor.reviews.*`)
  **Guardrail: nothing else. Do NOT touch `reviews` schema, other order/PDP components (add NEW component files only; do not edit `p/[slug]/page.tsx` or `orders/[id]/page.tsx` — mount via the existing sections if a slot exists, else your component is reachable standalone), `main.py`, db.ts. No migration.**

## 4. Implementation spec

- **`reviews.py`** (auth, uniform envelope, rate-limited): `POST /reviews` — **verified-purchase gate**: the `order_item_id` must belong to the authenticated customer AND the order is Delivered/Completed (else 403); rating 1–5, ≤3 photos (public bucket), one-per-order_item (UNIQUE → 409 on dup); editable within **7d**. `POST /reviews/{id}/reply` — vendor of the reviewed item only, one reply, editable **24h**. Non-purchaser → 403 (API + RLS).
- **Components:** PDP reviews-section (list, photo lightbox via `CloudinaryImage`, write entry when eligible); review-prompt on the order page (post-delivery CTA); vendor reply page. 360px; copy via the three namespaces.

## 5–9. Security etc.

**Non-purchaser cannot submit** (API + RLS test); one review per order_item (UNIQUE); verified-purchase = own order_item + delivered; photos public via `CloudinaryImage`; edit windows (7d review / 24h reply); reply authz (only the item's vendor); no secrets.

## 10. Tests (RUN before reporting)

`test_reviews.py`: **verified-purchase gate** (non-purchaser → 403; purchaser on non-delivered → 403; delivered purchaser → ok); **one-per-item** (dup → 409); **edit windows** (7d review boundary, 24h reply boundary); **reply authz** (other vendor → 403); reply threading correct. `pnpm --filter customer build && pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Non-purchaser cannot submit (API + RLS); one per order_item; photos via `CloudinaryImage`; reply threading correct; edit windows enforced.
- [ ] `catalog.reviews.*` + `orders.reviewPrompt.*` + `vendor.reviews.*` appended (append-rule); 2 app builds + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P01 — Reviews: submission & vendor replies
**STATUS/FILES/DEVIATIONS** (verified-purchase enforcement path; how components mount without editing page.tsx; window enforcement) **/TESTS** (paste verified-purchase-gate + one-per-item + edit-windows + reply-authz + full-pytest tail) **/EXCERPTS** the verified-purchase gate + the one-per-item guard — nothing else **/QUESTIONS**
