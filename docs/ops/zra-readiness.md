# ZRA readiness & VSDC activation runbook (M15-P07)

Status at launch: **VAT OFF** — Vergeo5 operates on the **Turnover Tax** posture. Invoices
and receipts are issued with sequential numbers and TPIN placeholders, but **no VAT is
charged and no VAT lines are rendered**. This document is the swap-in runbook for when the
business crosses the VAT threshold and must fiscalise through ZRA's Smart Invoice / VSDC.

## 1. When VAT registration becomes mandatory

- **VAT registration threshold (Zambia):** turnover of **K800,000 over any 12-month
  period** (or a reasonable expectation of reaching it). Track platform-attributable
  turnover monthly; when the trailing-12-month sum approaches the threshold, begin the
  registration + VSDC onboarding steps below **before** flipping the flag.
- Turnover Tax applies below the threshold; VAT (standard rate) applies once registered.
- Registration is done with ZRA; a **TPIN** and VAT registration certificate are issued.

## 2. What is already in place (the seam)

- `services/api/app/services/invoicing/builder.py` — assembles receipt/tax-invoice
  payloads with a **gapless sequential number** (`public.next_invoice_no`) and VAT columns
  that are **present but zeroed** while `VAT_ENABLED_AT_LAUNCH = False`.
- `services/api/app/services/invoicing/pdf.py` — renders the payload snapshot to PDF and is
  **VAT-flag-aware**: `render_invoice_pdf(snapshot, vat_enabled=...)` toggles the VAT
  breakdown block. Off at launch (no VAT lines); the layout branch already exists.
- `services/api/app/services/invoicing/vsdc.py` — the **single VSDC seam**,
  `submit_to_vsdc_stub(payload)`. It records intent only and returns a deterministic
  placeholder fiscal code (`VSDC-STUB-<series>-<no>`). It is **not wired into the request
  path** at launch.
- `services/api/app/routers/invoices.py` — owner-scoped, signed, rate-limited download of
  the rendered PDF for customers and vendors.

## 3. VSDC / Smart Invoice activation steps

1. **Register for VAT with ZRA**; obtain the VAT-registered TPIN and credentials.
2. **Onboard to Smart Invoice / VSDC** (virtual or hardware SDC) and obtain the device
   endpoint, device serial, and API credentials. Store secrets in env only (never repo).
3. **Implement the live client** alongside the stub in `vsdc.py`, e.g.
   `submit_to_vsdc_live(payload) -> VsdcSubmissionResult`, calling the VSDC API and
   returning the real fiscal code / signature / QR data. Keep the `VsdcSubmissionResult`
   shape so callers are unchanged.
4. **Flip the flags** in `builder.py`: set `VAT_ENABLED_AT_LAUNCH = True` and
   `VAT_RATE_BPS_AT_LAUNCH` to the current standard VAT rate (basis points). Line-level VAT
   then computes via the existing integer-ngwee path (no float).
5. **Wire fiscalisation into issuance**: on `issue_receipt` / `issue_tax_invoice`, call the
   live VSDC client and persist the returned fiscal code alongside the invoice snapshot.
   Keep it **idempotent** (invoice number is the natural key) and behind the outbox/retry
   posture used for other external calls.
6. **Render fiscal artefacts**: extend `pdf.py` to print the VSDC fiscal code + QR once the
   `vat_enabled` branch is on. The VAT breakdown block already renders under that branch.
7. **Backfill / cutover**: decide the effective date; invoices issued before the flag stay
   Turnover-Tax; invoices after are VAT + fiscalised.

## 4. Invariants to preserve

- Money stays **integer ngwee** end to end; `Decimal` only at any external decimal boundary.
- Invoice numbers remain **gapless and sequential** via the `invoice_counters` **counter table**
  - `public.next_invoice_no()` (`FOR UPDATE` consume-in-transaction) — deliberately **not** a
    Postgres `SEQUENCE`, which is not gapless on rollback.
- Downloads stay **owner-scoped** (customer sees only own orders; vendor only own sales)
  and **rate-limited**; links are short-lived and HMAC-signed.
- No secrets in the repo; VSDC credentials live in env.

## 5. Test posture

- `services/api/tests/test_invoices.py` covers PDF render, receipt vs tax-invoice variant,
  the VAT-flag-aware branch (off vs on), IDOR (other customer / other vendor => 404), and
  signed-link tamper/expiry. Re-run and extend these when activating VSDC.
