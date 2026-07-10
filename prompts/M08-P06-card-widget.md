> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — card = `payments` rows (rail `card`). Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M08-P06 — Card via Lenco hosted widget

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **NO direct card API (PCI)** — card = the **Lenco hosted widget**. **`payments` (0006):** a card payment is a `payments` row `rail='card'` (state machine M08-P04); widget session ref in `lenco_reference` / details in `raw jsonb` — **no migration**. **Webhook merged (M08-P03):** the return-verify **cross-checks the webhook** (`webhook_events`). **Lenco client merged (M08-P02):** `query_status` for server-side verify.
- **Fulfilment ONLY after server-verified success** — a **spoofed success redirect** (client returns "success" without a Lenco-verified status) **must NOT confirm the order**. Verify = **status query to Lenco on return AND webhook cross-check**; mismatch → **hold + alert**. Customer app `localePrefix:"always"`. Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). i18n `checkout` namespace — **shared with M07-P07**; you own a nested **`card`** section (append-rule).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P06.

## 2. Objective & scope

Card via the Lenco hosted widget: a **widget session create + return handling** where **fulfilment happens only after a server-verified success** (Lenco status query + webhook cross-check); a spoofed return without verified status does not confirm; widget failure → back to the payment step with retry.
**Non-goals:** no direct card fields (PCI — widget only), no state machine internals (M08-P04 — use it), no order creation, no migration.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/payments_card.py` (widget session create + return callback + **server-side verify before fulfilment**) · `apps/customer/app/[locale]/(shop)/checkout/card/[paymentId]/page.tsx` (widget embed/redirect + return handling) · `services/api/tests/test_payments_card.py`
- **Modify:** `packages/i18n/messages/en/checkout.json` (append nested `card` section)
  **Guardrail: nothing else. Do NOT touch `checkout/pending/*`/`_components` (M07-P07), `payments/state.py`/`lenco/*` (M08-P04/P02 — call), `webhooks_lenco.py` (M08-P03), `main.py`, schema.**

## 4. Implementation spec

- **`payments_card.py`:** (1) **create a widget session** — a `payments` row (`rail='card'`, `initiated`) + a Lenco widget URL/session (via M08-P02); return the widget target to the client. (2) **return callback / verify** — on return, **do NOT trust the client's success claim**: perform a **Lenco `query_status`** AND **cross-check `webhook_events`**; **fulfil (drive the order forward) ONLY on a server-verified success** via M08-P04's `transition_payment`. **Mismatch (claimed success, Lenco says otherwise) → hold + alert log; no fulfilment.** The **verify + webhook can arrive in either order → converge to a single success handling** (idempotent — the payment reaches `success` once).
- **Card page:** embed/redirect to the widget; handle the return by calling the verify endpoint; on verified success → order confirmation; on failure → back to the payment step (M07-P05) with retry. All copy via `checkout` (`card.*`); 360px.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; **no card fields (PCI — widget only)**; fulfilment only after server-verified success (spoof-proof — tested); mismatch → hold+alert; idempotent verify/webhook convergence; no secrets.

## 10. Tests (RUN before reporting)

`test_payments_card.py`: **forged-return** (client claims success, Lenco status not success → order NOT confirmed, hold+alert); **verify-webhook race** (verify-first and webhook-first both → single success handling, idempotent); widget failure → retry path. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Spoofed success redirect without Lenco-verified status does NOT confirm the order (tested); mismatch → hold + alert.
- [ ] Verify + webhook (either first) converge to a single success handling; widget failure → retry; `checkout.card.*` nested (append-rule); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P06 — Card via Lenco hosted widget
**STATUS/FILES/DEVIATIONS/TESTS** (paste forged-return + verify-webhook-race + full-pytest tail) **/EXCERPTS** the server-side verify-before-fulfil — nothing else **/QUESTIONS** (flag F9b for live widget)
