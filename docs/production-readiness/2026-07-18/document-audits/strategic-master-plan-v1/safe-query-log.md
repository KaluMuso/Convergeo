# Safe Query / Probe Log — Strategic Master Plan v1.0 audit

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY · No secrets/PII/full references/dumps printed.
All probes were **read-only**. No writes, migrations, seeding, deploys, workflow activation, or payment actions were performed. Live DB/API re-probes were **denied by proxy egress policy** (recorded below) — DB/live facts are therefore inherited from the same-day foundation baseline and attributed as such.

Legend: **local repo** = read-only inspection of the cloned repository at HEAD `0b88723`; **HTTP** = outbound curl; **foundation** = fact reused from `../../foundation/*` (captured 2026-07-18 ~12:48–13:00 UTC by a session that held live access).

---

## 1. Foundation contract compliance

| # | Purpose | Target | Filter/scope | Result (count/outcome only) | Outcome |
| - | ------- | ------ | ------------ | --------------------------- | ------- |
| 1 | Confirm foundation exists (else stop) | `docs/production-readiness/2026-07-18/foundation/` | dir listing | 7 foundation files present | PROCEED |
| 2 | Read contract + schema + access inventories | 3 required foundation md files | full read | read OK | established labels/schema/practices |
| 3 | Read supporting baseline | `production-evidence.md`, `executive-baseline.md`, `critical-risk-register.md` | full read | read OK | reused as live evidence (attributed) |

## 2. Source document extraction

| # | Purpose | Target | Scope | Result | Outcome |
| - | ------- | ------ | ----- | ------ | ------- |
| 4 | Detect text vs image PDF | uploaded PDF | PyMuPDF text extract | 17 pages; ~2.7k chars (image-based) | needed render+vision |
| 5 | Render pages for vision read | PDF → PNG | zoom 2.2 (~158dpi), 17 pages | 17 PNGs written to scratch | read all 17 via vision |
| 6 | Transcribe document | 17 page images | full read | 75 decisions + tensions + model + arch + methodology + phases + sprint + KPIs + risks captured | source-document.md |

> Note: uploaded PDF `producer`=Ghostscript, `creationDate`=2026-07-18; harness pre-count said "101 pages" but the actual parse is **17 pages** — trusted the parser. Scratch renders live under `scratch_audit/` (temporary; not part of the audit deliverable).

## 3. Local repository probes (read-only; rank-3 evidence → PARTIAL for runtime)

| # | Purpose | Target | Filter | Result (count only) | Outcome |
| - | ------- | ------ | ------ | ------------------- | ------- |
| 7 | Backend framework | `services/api` | `fastapi` vs `django` imports | **181** fastapi files, **0** django; pyproject "Vergeo5 FastAPI backend", `fastapi>=0.115` | Q9 CONFLICT (FastAPI) |
| 8 | Payment provider | `services/api` | `lenco` vs `dpo/directpay` | **70** lenco, **0** dpo; `payments/lenco/*`, `webhooks_lenco.py` | Q19 CONFLICT (Lenco-only) |
| 9 | Search engine | repo | `meilisearch|meili` | **0** files | Q15 CONFLICT (no Meilisearch) |
| 10 | Search impl (positive) | `services/api` | FTS/RRF/pgvector/`search_documents` | **17** files | Q31 VERIFIED-design (Postgres hybrid) |
| 11 | Async worker | `services/api` | `celery` | **0** files | Q18 CONFLICT (no Celery) |
| 12 | Cache | `services/api` | `upstash|redis` | **0** files | Q17 CONFLICT (no Redis) |
| 13 | Courier integration | repo | `yango`, `zampost` | yango **12** (label enum `Literal['yango','indrive','other']`), zampost **0** | Q43/Q47 CONFLICT (manual dispatch) |
| 14 | Notifications | `services/api` | whatsapp/sms/email adapters | 110 whatsapp files; `notifications/adapters/{whatsapp,sms,email}`; `sms.py: AfricasTalking` | Q14 CONFLICT; Q68/OTP PARTIAL |
| 15 | SMS provider (correction) | `notifications/adapters/sms.py` | `AfricasTalking` | present (camelCase; initial regex missed) | Africa's Talking SMS adapter EXISTS |
| 16 | Ledger/escrow templates | `services/api/app/services` | `LedgerTemplate`, `post_transaction` | `LedgerTemplate` class w/ CHARGE_RECEIVED, ESCROW_HOLD, RELEASE_TO_VENDOR, COMMISSION_CAPTURE, COD_COLLECTED, PAYOUT_EXECUTED, CLAWBACK, REFUND_LANE; `post_transaction` 37× | Q22 escrow ledger PARTIAL (code present; R2 prepaid gap) |
| 17 | Dynamic QR + pickup | `services/api/app/services` | `tickets/qr.py`, `pickup`, `pickup_verify` | HMAC+60s present; pickup verify router present | Q50/Q33 PARTIAL (code) |
| 18 | Subscription tiers | repo | `subscription|vendor_tier|paid_tier` | **0** files | Q4 MISSING (deferred D3) |
| 19 | Migrations in repo | `supabase/migrations` | count + tail | **55** files; last = 0051–0055 | migration-drift CONFLICT vs live ≤0050 |
| 20 | n8n workflows in repo | `infra/n8n/*.json` | listing | **18** json (release-job, tickets-issue, order-jobs, event-release, backups, etc.) | vs 2 live (R3) |
| 21 | Decision supersession | `docs/plan/00-decisions.md` | full read | D18–D24 supersede Master Plan stack; cites "Master Plan L2/Q25" | reframes CONFLICTs as intentional |

## 4. Live HTTP / DB probes — ATTEMPTED, DENIED BY POLICY

| # | Purpose | Target | Scope | Result | Outcome |
| - | ------- | ------ | ----- | ------ | ------- |
| 22 | Re-probe API health/OpenAPI/catalog | `https://api.vergeo5.com/{healthz,readyz,openapi.json,catalog/listings}` | HEAD/GET, limit=1 | **proxy CONNECT 403** (org egress policy denial; `recentRelayFailures` host `api.vergeo5.com:443`) | NOT re-probed; **did not retry** per proxy policy; used foundation §1/§5 |
| 23 | Live SQL (safe pack) | `mcp.supabase.com` (Supabase MCP) | `BEGIN READ ONLY; SELECT count(*)…` intended | **proxy CONNECT 403** + interactive OAuth unavailable (non-interactive session) | NOT executed; **did not retry**; used foundation schema/aggregates |

> Per `/root/.ccr/README.md`: "Do not retry organization policy denials (403/407) — report them instead." Both denials are reported here and in `missing-and-conflicting-items.md §f`. No attempt was made to route around the policy or bypass RLS/credentials.

## 5. Aggregates reused from foundation (no fresh DB access this session)

Row-counts only, sourced from `../../foundation/production-evidence.md §5` & `database-schema-inventory.md` (captured 2026-07-18):
vendors **3** (demo) · vendor_listings **134** · products **150** · categories **74** · listing_images `demo/%` **134** · orders/payments/ledger_txns/tickets **0** · profiles/user_roles **3/3** · commission_rates **9** · delivery_zones **3** · feature_flags **5 (all false)** incl. `public_launch=false` · n8n live workflows **2 active**.

**No PII, secrets, payment references, addresses, phones, emails, NRC/TPIN, or raw rows were accessed or printed at any point.**
