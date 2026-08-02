> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P12 — Regulator/licence verification + expiry `[CODE]` ⚠ trust-critical

## 1. Context
**Wave W4.** Some categories cannot be sold honestly without a licence — pharmacy, agro-chemicals, alcohol, firearms-adjacent, financial and certain food services. Today the platform has **KYC tiers** (`kyc_records`, tiers 1–3, guarded lifecycle in `0056_kyc_integrity.sql`) but **no notion of a category-specific regulator licence with an expiry date**.

An expired licence displayed as valid is worse than no badge at all: it is the platform vouching for something it has not checked. Expiry must therefore be **computed at read time**, never a stored boolean somebody has to remember to flip.

**Type:** `[CODE]`.

## 2. Objective & scope
Vendors record regulator licences per category; admins verify them; the badge expires by itself.
**Non-goals:** automated regulator API integration; blocking sales (a follow-up decision — this pebble surfaces truth, it does not enforce it).

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_vendor_licences.sql` — **verify next-free at branch time** (expected `0083`)
- `services/api/app/routers/vendor_licences.py`, `admin_licences.py` (new; auto-discovered)
- `services/api/app/services/vendors/licences.py` (new)
- `apps/vendor/**/settings/licences/**`, `apps/admin/**/licences/**`
- `packages/i18n/messages/en/{vendor,admin,trust}.json`
- Tests

## 4. Implementation spec
- `vendor_licences`: `vendor_id`, `category_id` (or a regulated-class enum), `regulator` , `licence_number`, `issued_on`, `expires_on date not null`, `document_path` (**private Supabase Storage**, never Cloudinary — this is a KYC-class document), `status` (`pending|verified|rejected|revoked`), `verified_by`, `verified_at`.
- **Status is server-controlled**, moved only by a guarded transition with an `audit_log` row — mirror `0056_kyc_integrity.sql` and the KYC state machine. Never a raw UPDATE.
- **Validity is derived**: `verified AND expires_on >= current_date`. Do not store `is_valid`. A test must assert that a licence which expires overnight stops being valid **without any write occurring**.
- Public surfaces show a badge only while derived-valid; expiry silently removes it. Admin queue surfaces "expiring within 30 days".
- Reuse the KYC document-access pattern for signed, short-TTL URLs; documents are never public.

## 5. Security / conventions
RLS + FORCE RLS; documents in the private bucket with owner/admin-only policies; every admin decision audited via `AdminAuditedRoute`; licence numbers are commercially sensitive — never log them in full.

## 10. Tests (RUN before reporting)
- `test_expired_licence_is_not_valid_without_any_write` (freeze/advance the clock)
- `test_vendor_cannot_set_status` (DB-level refusal)
- `test_revoked_licence_badge_disappears_immediately`
- `test_licence_document_is_not_publicly_readable`
- `test_admin_verify_writes_audit_row`
- `test_expiring_soon_queue_window`
- Migration replay; RLS matrix; `uv run pytest -q`; `ruff`; `mypy`.

## 11. Acceptance criteria / DoD
- [ ] Validity derived at read time; no stored boolean.
- [ ] Status unwritable by the vendor; every decision audited.
- [ ] Documents private, signed, short-TTL.
- [ ] Badge appears only for verified-and-unexpired.
- [ ] Expiring-soon queue exists for admins.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P12 — Licence verification + expiry
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the clock-advance test · **EXCERPTS:** the derived-validity query · **QUESTIONS:** …
