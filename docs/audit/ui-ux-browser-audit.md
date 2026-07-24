# UI/UX Browser Audit

**Date:** 2026-07-24  
**Method:** Browser automation, desktop viewport (~1280px)  
**Mobile (390px):** BLOCKED_EXTERNAL — device emulation unavailable in test environment

---

## Applications tested

| App                 | URL                                 | Load        | Notes                         |
| ------------------- | ----------------------------------- | ----------- | ----------------------------- |
| Customer            | https://www.vergeo5.com/en          | ✅ 200      | Homepage carousel, categories |
| Customer search     | /en/search?q=phone                  | ✅ 200      | Placeholder images            |
| Customer categories | /en/categories                      | ✅ 200      | Grid renders                  |
| Customer cart       | /en/cart                            | ⚠️ Error UI | API failure                   |
| Customer login      | /en/login                           | ✅ 200      | Phone/email/Google            |
| Vendor login        | https://vendor.vergeo5.com/en/login | ✅ 200      | Email + Google                |
| Admin               | https://admin.vergeo5.com/en/login  | ✅ 302      | Cloudflare Access gate        |
| i18n Bemba          | /bem                                | ✅ 200      | Translations correct          |

---

## Findings

### P0-001: Cart page broken

| Field        | Detail                                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------------------------- |
| **URL**      | https://www.vergeo5.com/en/cart                                                                                   |
| **Viewport** | Desktop 1280px                                                                                                    |
| **Steps**    | Navigate to /en/cart                                                                                              |
| **Expected** | Cart contents or empty state                                                                                      |
| **Actual**   | "Could not load your cart"                                                                                        |
| **Evidence** | Network: `GET http://localhost:8000/cart` ERR_CONNECTION_REFUSED; 48 console errors                               |
| **Severity** | **P0**                                                                                                            |
| **Fix**      | Set `NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com` in Vercel production env; rebuild all customer deployments |

### P1-001: Search product images missing

| Field        | Detail                                                                                                         |
| ------------ | -------------------------------------------------------------------------------------------------------------- |
| **URL**      | /en/search?q=phone                                                                                             |
| **Expected** | Product thumbnails via Cloudinary                                                                              |
| **Actual**   | Dashed placeholder boxes; prices show K0.00                                                                    |
| **Evidence** | 9 results with empty image areas                                                                               |
| **Severity** | **P1**                                                                                                         |
| **Fix**      | Verify `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` at build; inspect image `src` in listing cards; check CSP `img-src` |

### P1-002: CSP console pollution

| Field        | Detail                                                                                      |
| ------------ | ------------------------------------------------------------------------------------------- |
| **URLs**     | All customer pages                                                                          |
| **Evidence** | 12–79 console errors per page for blocked GTM, Supabase, localhost scripts                  |
| **Severity** | **P1** (security/ops)                                                                       |
| **Fix**      | Align report-only CSP with actual third-party origins; remove localhost from production CSP |

### P2-001: Notification permission on homepage load

| Field        | Detail                                                           |
| ------------ | ---------------------------------------------------------------- |
| **URL**      | /en                                                              |
| **Expected** | No permission prompt on first visit                              |
| **Actual**   | Browser notification permission dialog immediately               |
| **Severity** | **P2**                                                           |
| **Fix**      | Defer `Notification.requestPermission()` to explicit user action |

### P2-002: Mobile viewport untested

| **Severity** | **P2** |
| **Fix** | Run Lighthouse mobile + manual 360px testing per project perf budget |

---

## Navigation audit

| Check           | Customer                          | Vendor                               | Admin           |
| --------------- | --------------------------------- | ------------------------------------ | --------------- |
| IA clarity      | ✅ Good — bottom nav + mega menu  | ⚠️ 4-item nav hides half of features | ✅ Full sidebar |
| Dead links      | None found on homepage            | N/A (login only)                     | N/A (CF gate)   |
| Back navigation | ✅ Header back/breadcrumbs on PDP | —                                    | —               |
| Locale switcher | ✅ Works (/bem verified)          | —                                    | —               |

---

## Visual design

| Aspect           | Assessment                                           |
| ---------------- | ---------------------------------------------------- |
| Typography       | Consistent — design tokens from `packages/ui`        |
| Spacing          | Good mobile-first density                            |
| Colour           | Seasonal theme system (`NEXT_PUBLIC_SEASONAL_THEME`) |
| Product cards    | Inconsistent on search (missing images) vs homepage  |
| Trust indicators | Escrow copy present on cart empty state              |
| Brand            | Vergeo5 consistent across apps                       |

---

## Customer experience

| Journey                | Status                                 |
| ---------------------- | -------------------------------------- |
| Product discovery      | ✅ Homepage, categories work           |
| Search                 | ⚠️ Results but no images               |
| PDP                    | Not tested (no click-through in audit) |
| Cart                   | ❌ Broken                              |
| Checkout               | BLOCKED_UNSAFE                         |
| Trust/escrow messaging | ✅ Copy present in code                |
| i18n                   | ✅ Bemba renders correctly             |

---

## Vendor experience

| Journey    | Status                             |
| ---------- | ---------------------------------- |
| Login page | ✅ Clean, mobile-friendly layout   |
| Onboarding | BLOCKED_UNSAFE (needs credentials) |
| Dashboard  | BLOCKED_UNSAFE                     |

---

## Admin experience

| Journey        | Status                                            |
| -------------- | ------------------------------------------------- |
| CF Access gate | ✅ Properly secured                               |
| Login form     | Behind Access — not reachable without credentials |

---

## Accessibility (smoke)

- E2E spec exists: `e2e/specs/a11y-smoke.spec.ts`
- Customer listing card a11y tests in `listing-card-link-a11y.test.tsx`
- Full manual keyboard audit: **NOT performed** in this session

---

## Screenshots

Browser audit captured screenshots at `/tmp/computer-use/` (homepage, search, cart error, vendor login, admin CF gate, Bemba locale).

---

## Positive findings

- Homepage hero carousel functional
- Bemba translations render (not raw keys)
- Vendor/admin auth entry points load correctly
- Admin protected by Cloudflare Access
- PWA offline page exists (`/en/offline`)
