> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 9 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — no migration, no `db.ts`. Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P01 — Payment abstraction & money primitives

## 1. Context

**Wave 9 (parallel ×6).** Grounded against as-built `master`:

- **Money validation already exists — REUSE it, do NOT duplicate** (the `formatK`-duplication lesson). `services/api/app/schemas/base.py` (M03-P10) already provides: `REFERENCE_CHARSET_RE = ^[-._A-Za-z0-9]+$`; `NgweeInt`/`SignedNgweeInt` (int-only, **float/str/bool rejected**); `OrderReference`/`PaymentReference`/`RefundReference` Annotated types that **validate** a `ord-`/`pay-`/`rfd-` string; `parse_ngwee`. **Import the charset + validators from `app.schemas.base` — never re-declare them.**
- Your **genuinely new** surface: (a) **ngwee ↔ decimal-major-unit string** conversion via **`Decimal` only** (e.g. `123456` ⇄ `"1234.56"`, ZMW 2dp) for the Lenco boundary — this does NOT exist yet; (b) reference **generation** (`ord-<encoded-id>`, `pay-*`, `rfd-*`) + **parse-into-parts** (base.py only validates a string, it doesn't build or decode one); (c) the **provider strategy interface** + registry.
- `app/services/` is an implicit namespace package — create `app/services/payments/` with its **own `__init__.py`**; **do NOT create `app/services/__init__.py`** (parallel add/add collision — every sibling subdir owns its own). Routers auto-discover; this pebble adds **no router** (pure service layer). Contract reference: `docs/ops/lenco/lenco-api-distilled.md`.
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P01. **No Lenco HTTP client here (M08-P02, W10).**

## 2. Objective & scope

The provider-agnostic payment seam (Lenco first; Flutterwave/PawaPay later — D11) + money/reference primitives: a strategy interface, a registry, `Decimal`-only ngwee↔major-string conversion with a ZMW currency guard, and the `ord-/pay-/rfd-` reference codec (generate + parse).
**Non-goals:** no Lenco client/HTTP (M08-P02), no ledger (M08-P05), no order creation (M07-P06), no webhooks (M11), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/payments/__init__.py` · `payments/base.py` (strategy `Protocol`: `initiate_collection`, `query_status`, `initiate_payout`, `resolve_account`, `verify_webhook` — signatures + typed DTOs, NO impl) · `payments/registry.py` (name→strategy lookup; unknown provider → clean error) · `payments/money.py` (`Decimal`-only ngwee↔`"1234.56"`; ZMW guard) · `payments/references.py` (generate + parse `ord-/pay-/rfd-`, reusing `REFERENCE_CHARSET_RE` from `app.schemas.base`) · `services/api/tests/test_money.py`
  **Guardrail: nothing else. Do NOT touch `app/schemas/base.py` (import from it), `main.py`, `app/services/__init__.py`, schema, or add deps.**

## 4. Implementation spec

- **`money.py`:** `ngwee_to_major_str(ngwee: int) -> str` and `major_str_to_ngwee(s: str) -> int` using **`Decimal` exclusively** (never `float`) — exact 2dp ZMW; reject NaN/inf/negative-where-invalid/>2dp; a `currency` guard that only allows `ZMW`. Round-trips are exact for `0`, odd ngwee (`1` → `"0.01"`), and max bigint.
- **`references.py`:** `make_order_reference(order_id) -> "ord-<enc>"` (+ `pay-`/`rfd-` twins) and `parse_reference(ref) -> (kind, id)`; encoded id stays within `REFERENCE_CHARSET_RE`; round-trips; unknown/invalid-charset/empty-suffix → `ValueError`. **Reuse `app.schemas.base` validators — do not re-implement charset checks.**
- **`base.py` + `registry.py`:** a `PaymentStrategy` `Protocol` with the 5 methods + request/result DTOs (Pydantic `StrictModel` from `app.schemas.base`); `registry.get(provider: str)` returns the registered strategy or raises a clean `unknown provider` error. Lenco is **registered by name only** (impl is M08-P02) — a placeholder/None-returning stub is fine, but the seam must be real.
- **No float in money paths** — anywhere a monetary value is computed, it is `int` ngwee or `Decimal`; **never `float`**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; no secrets; `Decimal` on money (float = review-blocking); provider errors are typed, not bare strings.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_money.py`: **ngwee↔"1234.56" goldens** (0, `1`→`"0.01"`, odd ngwee, max bigint); **>2dp / NaN / non-ZMW rejected**; **reference generate+parse round-trip** + invalid-charset/empty/unknown-prefix rejected; **registry unknown-provider clean error**; **no-float guard** (assert money helpers reject/never emit `float`). **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] `Decimal`-only conversion, exact 2dp ZMW, goldens pass; codec round-trips; unknown provider errors cleanly.
- [ ] Reuses `app.schemas.base` (no duplicated charset/validators); no float in any money path; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P01 — Payment abstraction & money primitives
**STATUS/FILES/DEVIATIONS** (state exactly what you reused from `app.schemas.base` vs newly built) **/TESTS** (paste ngwee-goldens + codec round-trip + no-float + full-pytest tail) **/EXCERPTS** `money.py` conversion + the strategy `Protocol` — nothing else **/QUESTIONS**
