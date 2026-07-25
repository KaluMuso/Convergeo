# Vendor Application — Pages & Components Audit

**Application:** Vendor (`apps/vendor`)  
**Base URL:** `https://vendor.vergeo5.com/{locale}`  
**Auth:** Supabase session + middleware `vendor` role (onboarding paths exempt)

---

## Route inventory (31 pages)

| Route                             | Page name         | Source file                      | Rendering       | Access    | Main APIs                      | Nav linked?           | State           |
| --------------------------------- | ----------------- | -------------------------------- | --------------- | --------- | ------------------------------ | --------------------- | --------------- |
| `/[locale]`                       | Dashboard / home  | `app/[locale]/page.tsx`          | Server→Client   | Vendor    | `GET /vendor/orders/dashboard` | ✅ Quick nav          | Working         |
| `/[locale]/login`                 | Login             | `(auth)/login/page.tsx`          | Server          | Public    | Supabase                       | —                     | Working         |
| `/[locale]/onboarding`            | KYC onboarding    | `onboarding/page.tsx`            | Server→Client   | Applicant | `/kyc/*`                       | Onboarding only       | Working         |
| `/[locale]/onboarding/status`     | KYC status        | `onboarding/status/page.tsx`     | Server→Client   | Applicant | `GET /kyc/status`              | —                     | Working         |
| `/[locale]/orders`                | Order queue       | `orders/page.tsx`                | Server→Client   | Vendor    | `GET /vendor/orders/queue`     | ✅ Quick nav          | Working         |
| `/[locale]/orders/[id]`           | Order detail      | `orders/[id]/page.tsx`           | Server→Client   | Vendor    | Confirm/pack/ship APIs         | From queue            | Working         |
| `/[locale]/listings`              | Listings list     | `listings/page.tsx`              | Server→Client   | Vendor    | `GET /vendor/listings`         | ✅ Quick nav          | Working         |
| `/[locale]/listings/new`          | Create listing    | `listings/new/page.tsx`          | Server→Client   | Vendor    | `POST /vendor/listings`        | From listings         | Working         |
| `/[locale]/listings/import`       | CSV import        | `listings/import/page.tsx`       | Server→Client   | Vendor    | `/listings/import/*`           | ❌ No link            | Working, hidden |
| `/[locale]/listings/[id]/edit`    | Edit listing      | `listings/[id]/edit/page.tsx`    | Server→Client   | Vendor    | PATCH listing                  | From list             | Working         |
| `/[locale]/profile`               | Store profile     | `profile/page.tsx`               | Server→Client   | Vendor    | `GET/PATCH /vendor/profile`    | ✅ Quick nav          | Working         |
| `/[locale]/services`              | Services list     | `services/page.tsx`              | Server→Client   | Vendor    | `/vendor/services`             | Home quick-start only | Working         |
| `/[locale]/services/new`          | New service       | `services/new/page.tsx`          | Server→Client   | Vendor    | POST service                   | —                     | Working         |
| `/[locale]/services/[id]/edit`    | Edit service      | `services/[id]/edit/page.tsx`    | Server→Client   | Vendor    | PATCH service                  | —                     | Working         |
| `/[locale]/events`                | Events list       | `events/page.tsx`                | Server→Client   | Vendor    | `/organiser/events`            | ❌ No nav             | Working, hidden |
| `/[locale]/events/new`            | New event         | `events/new/page.tsx`            | Server→Client   | Vendor    | POST event                     | —                     | Working         |
| `/[locale]/events/[id]/edit`      | Edit event        | `events/[id]/edit/page.tsx`      | Server→Client   | Vendor    | PATCH event                    | From list             | Working         |
| `/[locale]/events/[id]/tickets`   | Ticket types      | `events/[id]/tickets/page.tsx`   | Server→Client   | Vendor    | Ticket type APIs               | ❌ No link            | Working         |
| `/[locale]/events/[id]/scan`      | Gate scan         | `events/[id]/scan/page.tsx`      | Server→Client   | Vendor    | `/tickets/verify`              | ❌ No link            | Working         |
| `/[locale]/events/[id]/roster`    | Attendee roster   | `events/[id]/roster/page.tsx`    | Server→Client   | Vendor    | Roster API                     | Dashboard only        | Working         |
| `/[locale]/events/[id]/dashboard` | Event dashboard   | `events/[id]/dashboard/page.tsx` | Server→Client   | Vendor    | Stats API                      | Edit page             | Working         |
| `/[locale]/scan`                  | Order pickup scan | `scan/page.tsx`                  | Server→Client   | Vendor    | `POST /vendor/pickup/verify`   | ❌ No nav             | Working, hidden |
| `/[locale]/payouts`               | Payouts           | `payouts/page.tsx`               | Server→Client   | Vendor    | `/vendor/payouts`              | ❌ No nav             | Working, hidden |
| `/[locale]/payouts/method`        | Payout method     | `payouts/method/page.tsx`        | Server→Client   | Vendor    | POST method                    | From payouts          | Working         |
| `/[locale]/analytics`             | Analytics         | `analytics/page.tsx`             | Server→Client   | Vendor    | `GET /vendor/analytics`        | ❌ No nav             | Working, hidden |
| `/[locale]/reviews`               | Review replies    | `reviews/page.tsx`               | Server→Client   | Vendor    | `GET /reviews/vendor`          | ❌ No nav             | Working, hidden |
| `/[locale]/returns`               | Returns queue     | `returns/page.tsx`               | Server→Client   | Vendor    | `GET /returns/vendor`          | ❌ No nav             | Working, hidden |
| `/[locale]/disputes`              | Disputes list     | `disputes/page.tsx`              | Server→Client   | Vendor    | `/disputes/vendor/mine`        | ❌ No nav             | Working, hidden |
| `/[locale]/disputes/[id]`         | Dispute detail    | `disputes/[id]/page.tsx`         | Server→Client   | Vendor    | Respond + evidence             | Internal              | Working         |
| `/[locale]/jobs`                  | RFQ jobs          | `jobs/page.tsx`                  | **Client page** | Vendor    | `/provider/jobs`               | ❌ No nav             | Working, hidden |
| `/[locale]/jobs/[id]`             | Job detail        | `jobs/[id]/page.tsx`             | **Client page** | Vendor    | Quotes, complete               | —                     | Working         |

**Quick nav (`vendor-quick-nav.tsx`):** Home, Listings, Orders, Profile only.

---

## Shell & shared components

| Component                           | File                               | Role                           |
| ----------------------------------- | ---------------------------------- | ------------------------------ |
| VendorShell                         | `_components/vendor-shell.tsx`     | Header, theme, conditional nav |
| VendorQuickNav                      | `_components/vendor-quick-nav.tsx` | 4-item bottom nav              |
| VendorEmptyState / VendorErrorState | `_components/async-state.tsx`      | Load/error UX                  |
| KYC integrity guards                | `_lib/kyc-integrity.ts`            | Client-side tier honesty       |
| Vendor error mapper                 | `_lib/vendor-errors.ts`            | 401/403 → i18n keys            |

### Feature components (by domain)

- **Onboarding:** `onboarding-flow.tsx`, `kyc-docs-step.tsx`, `doc-capture.tsx`, `status-screen.tsx`
- **Listings:** `listing-create-flow.tsx`, `listing-edit-form.tsx`, `image-manager.tsx`, `import-flow.tsx`
- **Orders:** `order-card.tsx`, `action-bar.tsx`
- **Events:** `event-form.tsx`, `ticket-type-config.tsx`, `scanner-view.tsx`, `roster-view.tsx`
- **Payouts:** `payouts-view.tsx`, `payout-method-form.tsx` (PDF statement stub)

---

## Middleware protection

```text
apps/vendor/middleware.ts
  → updateSession() (Supabase cookie refresh)
  → shouldRedirectToLogin("vendor", ...)
  → Exempt: /login, /onboarding, /onboarding/status
  → Requires JWT app_metadata.roles includes "vendor"
```

---

## Risks

| ID    | Severity | Finding                                          |
| ----- | -------- | ------------------------------------------------ |
| R-004 | P1       | 15+ implemented routes not in primary navigation |
| R-020 | P2       | No staff/RBAC (documented VEND-10 out of v1)     |
| R-021 | P3       | PDF payout statement shows stub copy             |
| R-022 | P3       | T2 KYC upgrade stub in status screen             |

---

## Production evidence

- `GET https://vendor.vergeo5.com/en/health` → 307 (locale redirect)
- Login page loads with email + Google auth
- Middleware redirects unauthenticated users to `/login`
