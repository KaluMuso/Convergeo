# Vergeo5 data retention & DPA handling

This document describes what happens when a customer exercises Zambia Data Protection Act (DPA) rights via **export** or **account deletion** (`POST /account/export`, `POST /account/delete`). It complements the public privacy policy at `/legal/privacy`.

## Summary

| Category                                     | On deletion                                       | Retention window                                                    | Reason                                                     |
| -------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------- |
| Profile name, phone, notification prefs      | **Removed / anonymized**                          | —                                                                   | No longer needed after account closure                     |
| Saved addresses                              | **Hard-deleted**                                  | —                                                                   | Delivery PII; not required for tax/audit                   |
| Orders, order items, checkout totals         | **Retained, PII stripped**                        | **7 years** after order completion                                  | ZRA audit trail, dispute evidence, platform reconciliation |
| Payments (amounts, rails, Lenco refs)        | **Retained, PII redacted in `raw`**               | **7 years**                                                         | Financial audit, chargeback/dispute support                |
| Invoices (series/number, amounts, VAT flags) | **Retained, customer PII redacted in `snapshot`** | **7 years**                                                         | Sequential invoice integrity (ZRA-ready)                   |
| Ledger transactions & postings               | **Untouched**                                     | **7 years minimum**                                                 | Double-entry escrow audit; amounts/accounts immutable      |
| Reviews (rating retained)                    | **Body/photos cleared**                           | Life of anonymized order record                                     | Verified-purchase integrity without personal commentary    |
| Disputes / returns evidence                  | **Evidence paths cleared**                        | Case metadata while order retained                                  | Remove uploaded PII while preserving case outcome          |
| Auth login (`auth.users`)                    | **Removed or permanently banned**                 | —                                                                   | Re-login must be impossible                                |
| Export JSON bundles (Storage)                | **Auto-expire via short-lived signed URL**        | **15 minutes** download window; objects purged per bucket lifecycle | Transient DPA portability artefact                         |

## Deleted vs anonymized-and-retained

### Hard-deleted

- All rows in `addresses` for the user.
- Notification channel preferences on `profiles.notif_prefs`.
- Login capability: Supabase Auth user is deleted when FK constraints allow; otherwise the account is **banned indefinitely** and phone/email credentials are stripped so re-authentication is impossible.

### Anonymized but retained

- **`profiles`**: `display_name` → `Deleted User`, `phone` → null, `notif_prefs` → `{}`, `deleted_at` set. Row kept because `orders.customer_id` references `auth.users` with `ON DELETE RESTRICT`.
- **`orders`**: monetary fields, status history, vendor linkage, and IDs unchanged; `address_id` and `delivery_zone` cleared.
- **`order_items`**, **`checkout_groups`**: unchanged amounts/qty snapshots (product titles are catalog snapshots, not customer PII).
- **`payments`**, **`invoices`**: transactional amounts and references kept; nested JSON snapshots redacted.
- **`reviews`**: star rating kept for aggregate vendor metrics; free-text body and photo paths cleared.
- **`disputes`**, **`returns`**: status/lane/amount metadata kept; private evidence object paths cleared.
- **`ledger_*`**: **never modified** on customer deletion — required for escrow reconciliation and tax audit.

### Never exported to the customer bundle

- **`ledger_accounts`**, **`ledger_transactions`**, **`ledger_postings`**: service-role-only; not customer-readable under RLS. Export covers customer-visible financial artefacts (`payments`, `invoices`) only.

## Export flow

1. Authenticated customer calls `POST /account/export`.
2. API reads all RLS-scoped tables via the **user-token Supabase client** (proves the caller owns the rows).
3. JSON bundle uploaded to the **`private-artifacts`** bucket at `data-exports/{user_id}/{export_id}.json`.
4. API returns a **signed download URL** valid for **900 seconds (15 minutes)**.

## Deletion flow (confirmation friction)

1. Customer types the exact phrase **`DELETE MY ACCOUNT`**.
2. Customer enters a **fresh SMS OTP** sent to their registered phone (re-auth).
3. On success, server (service-role, explicit `user_id` filter):
   - deletes addresses;
   - anonymizes profile + order-linked PII;
   - redacts invoice/payment JSON snapshots;
   - clears review/dispute/return evidence;
   - removes or permanently bans the Auth user.

Deletion is **idempotent**: repeat requests after `profiles.deleted_at` is set are safe no-ops.

## Legal / operational notes

- **ZRA**: seven-year retention aligns with common Zambian tax record-keeping practice; legal counsel to confirm final policy (F4).
- **Child accounts**: not supported at launch; deletion path assumes adult account holder.
- **Vendor accounts**: this pebble covers **customer** DPA flows only; vendor KYC artefacts follow separate retention in the private KYC bucket (admin-reviewed, not customer-exported here).

## Related code

- API router: `services/api/app/routers/privacy.py`
- Customer UI: `apps/customer/app/[locale]/account/privacy/page.tsx`
- Privacy policy: `apps/customer/app/[locale]/(marketing)/legal/privacy/page.tsx`
