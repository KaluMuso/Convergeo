> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free (`httpx` + `respx` already available). **Run the FULL `uv run pytest` before reporting.**

# M08-P02 — Lenco API client

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **Payment seam merged (M08-P01):** `app/services/payments/{base.py (PaymentStrategy Protocol), registry.py, money.py, references.py}`. **You implement the Lenco strategy behind that Protocol and register it** (replace the `_LencoPlaceholderStrategy`). **Amounts cross the boundary as decimal-major strings via `payments.money` converters** (`ngwee_to_major_str`/`major_str_to_ngwee`) — never float, never raw ints to Lenco.
- Create **`app/services/payments/lenco/`** with its **own `__init__.py`** (parent `payments/` exists). Rails: **MTN + Airtel** collections (USSD-push); **Zamtel behind a config flag pending F9a**. Contract reference: `docs/ops/lenco/lenco-api-distilled.md` (webhook sig = HMAC-SHA512(raw, SHA256(api-token)); amounts decimal-major at boundary).
- **Secrets from env ONLY** — `lenco/config.py` holds sandbox/prod base URLs + **token env names** (never values; `.env.example` names only if needed, but do NOT commit secrets). **Tests are `respx`-mocked against recorded sandbox fixtures — F9b (live sandbox creds) is NOT required to build or test this pebble** (only live E2E, deferred). No router here (webhook endpoint = M08-P03, W11).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P02.

## 2. Objective & scope

A typed Lenco HTTP client: collections (MoMo USSD-push MTN/Airtel; Zamtel flag-gated), transaction status query, `/resolve` account-name, payouts (MoMo + bank), a **typed error taxonomy** (declined/timeout/insufficient/invalid-number), timeouts + **bounded retries on idempotent GETs only**, all amounts via the P01 decimal converters.
**Non-goals:** no webhook endpoint (M08-P03), no card widget (M08-P06), no ledger (M08-P05), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/payments/lenco/__init__.py` · `lenco/client.py` (the httpx client) · `lenco/models.py` (typed request/response contracts per the distilled doc) · `lenco/config.py` (base URLs + token env names; sandbox/prod) · `services/api/tests/test_lenco_client.py` (respx-mocked)
- **Modify (register the strategy):** `app/services/payments/registry.py` **ONLY IF** M08-P01 left registration to the client; if M08-P01 already registers a placeholder, prefer swapping via its documented hook. If editing `registry.py` risks a conflict, instead expose a `LencoStrategy` from `lenco/` + a `TODO(wire)` and note it — **do not fight M08-P01's registration seam.**
  **Guardrail: nothing else. Do NOT touch `payments/{base,money,references}.py` (import), `main.py`, schema, or add deps.**

## 4. Implementation spec

- **`client.py`:** async `httpx` client implementing the `PaymentStrategy` methods — `initiate_collection` (MoMo USSD push; rail MTN/Airtel, Zamtel only if the config flag is on), `query_status`, `resolve_account` (`/resolve`), `initiate_payout` (MoMo + bank), `verify_webhook` (HMAC-SHA512(raw, SHA256(token)) per the distilled doc). **Amounts to/from Lenco are decimal-major strings via `payments.money`.** **Timeouts on every call; bounded retries (with backoff) ONLY on idempotent GETs** (status/resolve) — never retry a collection/payout POST.
- **`models.py`:** typed request/response DTOs (Pydantic `StrictModel`) mirroring the distilled contract; **every call typed both directions**. **Error taxonomy:** map Lenco failures to `declined | timeout | insufficient | invalid_number | provider_error` (typed, not bare strings).
- **`config.py`:** sandbox vs prod base URLs; token via `os.environ[...]` (env-name constants only). No secret literals.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; secrets env-only (never repo); retry only on safe GETs; amounts decimal-major via P01 (no float); webhook-sig verify per contract; no secrets committed.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_lenco_client.py` (respx): **contract tests vs recorded sandbox fixtures** (collection init, status, resolve, payout — request + response shapes); **error-taxonomy mapping** (declined/timeout/insufficient/invalid-number); **retry only on safe methods** (a collection POST is NOT retried; a status GET is); amounts serialized as decimal-major strings. **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Every call typed both directions; amounts cross as decimal-major strings via P01; error taxonomy mapped; retries only on idempotent GETs.
- [ ] Secrets from env only (no literals); registered behind M08-P01's `PaymentStrategy` seam; full API suite + repo green.
- [ ] **F9b note:** live sandbox E2E documented as the follow-up gate; this pebble is fully covered by mocked fixtures.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P02 — Lenco API client
**STATUS/FILES/DEVIATIONS** (how you registered behind M08-P01's seam) **/TESTS** (paste contract + error-taxonomy + retry-safety + full-pytest tail) **/EXCERPTS** the collection call (amount via money converter) + webhook-sig verify — nothing else **/QUESTIONS** (flag F9b for live E2E)
