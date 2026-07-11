> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel batch 1). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master` to compare against a clean baseline, never stash). **⚙ CI GATING:** any DB-touching test must be isolation-clean; converger may wire it into the rls step. **Run the FULL `uv run pytest` before reporting.**

# M15-P07 — ZRA invoicing surfaces & VSDC seam

## 1. Context

**Grounded against as-built `master` — the invoicing seam ALREADY PARTLY EXISTS. RECONCILE, do NOT duplicate:**

- **`services/api/app/services/invoicing/` already has `vsdc.py`, `builder.py`, `allocation.py`.** `vsdc.py` already defines `VsdcSubmissionResult` + `submit_to_vsdc_stub(payload)` (the documented VSDC seam). **Do NOT create a second `vsdc_stub.py` — extend/keep the existing `vsdc.py`.** `builder.py` already assembles invoice data — reuse it; add the PDF renderer + the customer/vendor download router on top.
- **No `services/api/app/routers/invoices.py` yet** — create it (signed download for customer + vendor).
- **The M09-P05 invoice stub is in the customer app:** `apps/customer/app/[locale]/account/orders/_components/invoice-link.tsx` + `orders-api.ts` + `[id]/page.tsx`. Wire the real signed-download endpoint into `invoice-link.tsx` (replace the stub link target). Money is integer **ngwee** — never float; render via `formatK`.
- **VAT flag OFF at launch** (Turnover-Tax posture); layout must be VAT-flag-aware (VSDC seam for later). Sequential invoice numbers + TPIN fields.
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P07.

## 2. Objective & scope

Tax-invoice + receipt PDF (sequential no, TPIN, Turnover-Tax posture, VAT-flag-aware), signed customer/vendor download endpoint, VSDC activation doc + ZRA-readiness runbook, and replacement of the M09-P05 stub link with the real download.
**Non-goals:** no live VSDC/ZRA call (seam + stub only), no VAT-on layout activation, no migration (invoice numbers derive from the existing order/invoice sequence — reuse it; do NOT add a new sequence table without confirming none exists).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/invoicing/pdf.py` (tax-invoice + receipt PDF renderer — reuse `builder.py`'s data assembly) · `services/api/app/routers/invoices.py` (customer + vendor signed download; auth + owner-scoped + rate-limited) · `docs/ops/zra-readiness.md` (K800k/12mo threshold, VSDC activation runbook) · `services/api/tests/test_invoices.py`
- **Modify:** `services/api/app/services/invoicing/vsdc.py` (ONLY if the activation-doc seam needs a docstring/interface tweak — prefer leaving it) · `apps/customer/app/[locale]/account/orders/_components/invoice-link.tsx` (point at the real signed download) · `services/api/app/main.py` (register the invoices router ONLY — one line; if a converger conflict risk, note it in the report instead)
  **Guardrail: nothing else. Do NOT touch `allocation.py`, ledger, db.ts, migrations, other routers, `orders-api.ts` beyond the one download-URL call if strictly needed. No new i18n namespace.**

## 4. Implementation spec

- **`pdf.py`:** render from `builder.py`'s assembled invoice dict → PDF bytes. Fields: sequential invoice no, seller/buyer TPIN placeholders, line items (qty × unit ngwee → `formatK` display), totals, Turnover-Tax note. **VAT-flag-aware:** a `vat_enabled` bool toggles a VAT breakdown block — OFF at launch (no VAT lines rendered), but the layout branch exists.
- **`invoices.py`:** `GET /invoices/{order_id}` (customer, owner-scoped) + vendor-scoped variant; returns a short-lived signed URL or streams the PDF; rate-limited; 404 for non-owner (no IDOR leak).
- **`vsdc.py`:** keep `submit_to_vsdc_stub` as the single seam; the activation runbook (`zra-readiness.md`) documents the swap to a live client. Do NOT wire it into the request path (launch = stub-only).
- **`invoice-link.tsx`:** replace the stub target with the real `/invoices/{order_id}` download; keep i18n keys already used (do NOT add marketing/legal keys — M16-P04/M15-P06 own those).

## 5–9. Security etc.

Owner-scoped download (customer sees only own orders; vendor only own sales — assert no IDOR in a test); signed/short-lived URL; integer ngwee only (no float); TPIN/tax fields are placeholders, no real secrets; VAT off; VSDC stub not in the live path.

## 10. Tests (RUN before reporting)

`test_invoices.py`: PDF renders for a delivered order (bytes non-empty, sequential no present); **IDOR** (other-customer / other-vendor → 404); VAT block absent while `vat_enabled=false`; receipt vs tax-invoice variant. `pnpm --filter customer build`, `pnpm typecheck/lint`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Reuses the existing `invoicing/` seam (no duplicate vsdc_stub); PDF VAT-flag-aware (off at launch); signed owner-scoped download (no IDOR); stub link replaced.
- [ ] ZRA-readiness + VSDC activation doc present; no migration; customer build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P07 — ZRA invoicing surfaces & VSDC seam
**STATUS/FILES/DEVIATIONS** (how you reconciled with the existing `vsdc.py`/`builder.py`; the VAT-flag-aware branch; the signed-download authz) **/TESTS** (paste IDOR + render + VAT-off + full-pytest tail) **/EXCERPTS** the download authz check + the VAT-flag layout branch — nothing else **/QUESTIONS**
