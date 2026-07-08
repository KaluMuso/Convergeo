> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN — no migration** (the tables you need already exist). Stay dep-free.

# M12-P02 — KYC backend & caps enforcement

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master` — **the schema already exists, do NOT add a migration:**

- **`public.kyc_records`** (`0002`): `vendor_id`, `status`, `momo_name_match jsonb`, `updated_at` (+trigger). **`public.vendors`**: `status` (`draft|pending_kyc|active|suspended`), `kyc_tier` (1/2/3), `caps_snapshot jsonb`, `preferred_badge bool` — **these are server-controlled** (a guard trigger raises if a client tries to change `status`/`kyc_tier`; you mutate via the **service-role client**).
- **`public.vendor_quotas`** (`0008`): per-tier `max_listings`, `first_orders_cap_ngwee` — **caps read from here** (not hardcoded). COD cap in `platform_config.cod_cap_ngwee`.
- API: routers auto-discover (never edit `main.py`); `core/auth.py` (`require_role`, `get_current_user`), service-role client confined to `app/supabase_client.py`. Lenco `/resolve` contract in `docs/ops/lenco/lenco-api-distilled.md` (momo name-match). `httpx` available.
- **`app/services/` does NOT exist** — create `app/services/kyc/` (own `__init__.py`); **do NOT create `app/services/__init__.py`** (implicit namespace package).
- **Interface edge with M12-P01 (same wave, UI):** you own the endpoint contract M12-P01 codes against — keep it documented in the report.
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P02.

## 2. Objective & scope

Server-side KYC status machine (draft→submitted→approved|rejected; T1/T2/T3), momo name-match via Lenco `/resolve` (recorded in `kyc_records.momo_name_match`), and caps enforced as FastAPI dependencies (30-listing cap, first-5-orders ≤ COD cap each, payout velocity — from `vendor_quotas`/`platform_config`), plus the Preferred-badge job.
**Non-goals:** no onboarding UI (M12-P01), no listing-create route (M12-P03 — you provide the caps _dependency_ it will use), no new schema, no payout execution (M08).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/kyc/__init__.py` + `{state_machine,name_match,badge}.py` · `services/api/app/services/kyc/caps.py` (enforcement dependencies) · `services/api/app/routers/kyc.py` · `services/api/tests/test_kyc_caps.py`
  **Guardrail: nothing else. No migration/`db.ts` (schema frozen; tables exist), no `app/services/__init__.py`, no `main.py`, no UI.**

## 4. Implementation spec

- **State machine (`state_machine.py`):** guarded transitions draft→submitted→approved|rejected, resubmit; T1/T2/T3 progression. **All `vendors.status`/`kyc_tier` writes go through the service-role client** (client writes are blocked by the guard trigger); every transition writes `audit_log` (before/after) — reuse the M13-P01 audit path if applicable, else write directly via service-role.
- **Name-match (`name_match.py`):** call Lenco `/resolve` (httpx) with the MoMo number; record the result + match score in `kyc_records.momo_name_match`; a mismatch is flagged (does not auto-approve).
- **Caps (`caps.py`):** FastAPI **dependencies** reading `vendor_quotas` (per tier) + `platform_config`:
  - **listing cap** — 31st listing for T1 → **403 with i18n reason** (dependency for the future listing-create route);
  - **first-orders cap** — first 5 orders each ≤ `cod_cap_ngwee`; a K500+1ngwee order in the first 5 → blocked; 6th order unrestricted;
  - **payout velocity** — per quotas.
    Enforce **server-side** as injectable dependencies (so M12-P03/order-accept just add `Depends(...)`).
- **Preferred badge (`badge.py`):** idempotent monthly job — grant/revoke on ≥20 orders, ≥4.5★, <2% disputes, <5% cancels; audited.
- **`kyc.py`:** submit/status/resubmit endpoints (the contract M12-P01 uses); admin approve/reject is M13 (KYC queue) — expose only what onboarding needs here.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

N/A UI. **Security:** status/tier server-controlled (guard trigger + service-role only); caps enforced server-side (client cannot bypass); name-match mismatch never auto-approves; roles from DB; no secrets (Lenco token from env).

## 10. Tests (RUN before reporting — `uv run pytest`, `ruff`, `mypy --explicit-package-bases`)

`test_kyc_caps.py`: **every cap boundary** — 31st listing (T1) → 403 i18n; 6th order unrestricted; **K500+1ngwee blocked in first 5**; T2 lifts caps; **badge grant/revoke** idempotent (fixtures); **name-match mismatch handling** (recorded, not approved); tier transitions audited. State-machine illegal transitions rejected.

## 11. Acceptance criteria / DoD

- [ ] 31st T1 listing → 403 (i18n); 6th order unrestricted; K500+1ngwee blocked in first 5; T2 lifts caps.
- [ ] Caps are injectable server-side dependencies (reusable by listing-create/order-accept); status/tier via service-role only.
- [ ] Badge job idempotent; name-match recorded; no migration/db.ts; ruff+mypy+pytest green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M12-P02 — KYC backend & caps enforcement
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste every cap boundary + badge + name-match output
**EXCERPTS:** `caps.py` enforcement dependencies + the state-machine transition guard — nothing else
**QUESTIONS:** (or "none") — state the kyc endpoint contract you exposed for M12-P01
