# R02 prompt pack — dispatch guide

> **Superseded in part by `prompts/R02-C01-continue-after-rg6.md` (2026-08-02).** Read C01 first:
> it carries RG-6 (the RLS matrix was never testing RLS), the D36/D37 reconciliation, the open half
> of G8, and the current next-free migration number. Where the two disagree, C01 is newer.

**Wave plan:** `docs/plan/00-status.md` → "Current release gates" · **Evidence base:** `docs/production-readiness/2026-08-01/vision-audit-rescore.md`
**Governing decisions:** **D36** (wholesale omission, amends D28) and **D37** (social commerce, not a social network) in `docs/plan/00-decisions.md`.

## Session bootstrap (read in this order, every new session)

1. `AGENTS.md` — branch policy, toolchain gotchas, health-check paths
2. `CLAUDE.md` — stack, conventions, Zambia guardrails
3. `docs/plan/00-status.md` — current gates (**not** the history callouts)
4. `docs/plan/00-decisions.md` — D1–D37, especially **D15, D28, D35, D36, D37**
5. `docs/production-readiness/2026-08-01/vision-audit-rescore.md` — what is actually closed
6. The pebble's own prompt, with `prompts/_header.md` prepended **verbatim**

Never re-read `docs/concept/*.pdf` or `docs/ops/lenco/*.pdf` — distillations exist.

## Status — what is already done (do NOT redo)

| Pebble      | State                         | Evidence                                                                                                                                                                                                                                                                                        |
| ----------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R02-P01** | **DONE** (code half)          | `check-staging-schema.sh` now fails closed; `check-db-reachable.sh` added; self-test **16 passed, 0 failed, 0 skipped**. **Operator half open:** `STAGING_SUPABASE_DB_URL` still holds a direct IPv6-only host — repoint it at the session pooler (`aws-0-eu-west-1.pooler.supabase.com:5432`). |
| **R02-P05** | **DONE**                      | D36 implemented on PDP + comparison: an emptied page now 404s identically to an absent product. 6 + 3 tests, proven to fail without the fix. Facet counts and the vendor storefront were checked and correctly need no change — see the commit.                                                 |
| **R02-P06** | **DONE** (proof, no new code) | Status is already server-controlled by `0038`'s guard trigger, and the cart already re-derives eligibility. The untested gap was `suspended`; failure-path tests added, verified to fail against a loosened rule.                                                                               |
| **R02-P03** | **BLOCKED — operator**        | Staging is at `0001`–`0079`; production is at `0071`. Applying to production is deploy-class and needs founder authorisation plus a backup (VA-P00) first.                                                                                                                                      |
| **R02-P02** | **BLOCKED — egress**          | Needs a host that can reach `api.vergeo5.com` / `*.vergeo5.com`.                                                                                                                                                                                                                                |
| **R02-P10** | **DONE** (API)                | `app/services/vendors/hours.py` + `open_now`/`next_open_at` on directory locations + opt-in `?open_now=true`. 29 + 5 tests. **Remaining:** catalog wiring, customer filter UI.                                                                                                                  |
| **R02-P07** | **DONE** (schema)             | `0080` — label, structured address, `phone_e164`, `is_primary` (partial unique index), `status`; public policy now hides closed branches. Verified on real Postgres. **Remaining:** vendor branch editor, exposing label/phone on the seven read paths.                                         |
| **R02-P08** | **DONE** (schema)             | `0081` — `listing_location_stock`, ownership-guard trigger, backfill to the primary branch. **Oversell proven with real threads** (8 threads/1 unit → 1 winner). **Remaining:** routing cart/checkout through the per-branch claim, PDP availability.                                           |
| **R02-P13** | **DONE** (schema)             | `0082` — enquiry threads/messages. C2C is **structurally unrepresentable**; no attachment column; two-party RLS proven (non-party sees 0). **Remaining:** routers, outbox notification, rate limits, content screen.                                                                            |
| **R02-P14** | **DONE** (schema)             | `0083` — `vendor_follows` + `vendor_follower_count()`. Vendor gets a count, never identities (proven: count=2, rows=0). **Remaining:** follow router, new-listing notification, share pages.                                                                                                    |
| CI gate     | **DONE**                      | `RLS isolation matrix` is now **blocking** — it previously carried `continue-on-error`, so an RLS regression would have shipped green.                                                                                                                                                          |

Everything else (P02 evidence, P03 apply, P04, P09, P11, P12, P15–P20) is unstarted.
**P12 is the next unstarted schema pebble; the highest-value work overall is wiring the P08 claim path into cart/checkout.**

### Migration numbers actually used

`0080` (P07) · `0081` (P08) · `0082` (P13) · `0083` (P14). **Next free is `0084`** — still verify at branch time.

### Standing caveat for every schema pebble above

`packages/types/src/db.ts` and `services/api/tests/rls/test_matrix.py` entries were **hand-authored**, because generating them needs a Supabase stack the authoring session could not run. Two CI jobs are the authority — `Database / typegen drift` and the now-blocking `RLS isolation matrix`. If either diffs, **apply its exact output**; do not argue with it. The M17/M18 commits record the same lesson.

## Order and dependencies

| Wave                   | Pebbles               | Depends on                        | Can run in parallel? |
| ---------------------- | --------------------- | --------------------------------- | -------------------- |
| **W1** runtime truth   | P01 → P02 → P03 → P04 | P02 needs P01                     | P03 ∥ P04 after P02  |
| **W2** B2B correctness | P05 → P06             | P05 first (shares `access.py`)    | no                   |
| **W3** real data       | P07 → P08, P09        | P08 needs P07                     | P09 ∥ P08            |
| **W4** discovery       | P10, P11, P12         | P10/P11 need P07                  | all three ∥          |
| **W5** social          | P13, P14              | P14 touches D36 paths — after P05 | P13 ∥ P14            |
| **W6** depth           | P15, P16, P17, P18    | P17 needs P05/P06/P08             | P15 ∥ P16 ∥ P18      |
| **W7** verification    | P19 → P20             | after W1–W6                       | no                   |

**W1 and W2 gate everything.** Do not start W3+ against a staging plane whose evidence is not trustworthy (that is exactly what R02-P01 fixes).

## Migration numbers

**Superseded by the "actually used" list above.** The original plan expected
`0080`–`0088`; four of those numbers are now taken by different pebbles than
planned, because P06 needed no migration (the `business_buyers` guard already
existed in `0038`) and everything shifted down by one.

**Taken:** `0080` P07 · `0081` P08 · `0082` P13 · `0083` P14.

| Pebble | Expected next | Subject                |
| ------ | ------------- | ---------------------- |
| P12    | `0084`        | vendor licences        |
| P15    | `0085`        | storefront collections |
| P16    | `0086`        | product classes        |
| P17    | `0087`        | warehouses, lots, RFQ  |

**Every implementer must still verify next-free at branch time.** Duplicate
prefixes have shipped to master four times and `schema_migrations` keys on the
numeric prefix, so a collision is a fatal replay error, not a merge conflict.
`scripts/ci/migration-replay.sh` has a fail-fast duplicate-prefix guard — run
it before opening a PR.

## Required MCP connections by pebble type

| Work                            | Needs                                                                    |
| ------------------------------- | ------------------------------------------------------------------------ |
| Schema / RLS (P06–P08, P12–P17) | **Supabase** (`list_migrations`, `execute_sql`, `get_advisors`)          |
| Deployment evidence (P02, P03)  | **Supabase** + **Vercel** + **GitHub Actions**                           |
| n8n workflows (P04)             | **n8n** (`search_workflows`, workflow read)                              |
| Media (P09, P11)                | **Cloudinary**                                                           |
| Browser pass (P19)              | Pre-installed Chromium + Playwright — **never** run `playwright install` |

Two Supabase projects exist and they are **not** interchangeable: **`vergeo-sandbox`** (`iyasmrmbcrvlfxpzescb`) is staging and carries `0001`–`0079`; **`Vergeo5`** (`dpadrlxukcjbewpqympu`) is production and is at `0071`. Read the project ref before every write-shaped action.

## Standing rules for every pebble

- One pebble = one branch = one PR titled `R02-P{nn}: {title}`. Conventional commits.
- `git status --short` first; **preserve unrelated changes**; never stash/reset/checkout over someone else's work.
- **Money is integer ngwee.** `Decimal` only at the Lenco boundary. **Float on money is a review-blocking bug.**
- Zero hardcoded user-facing strings — next-intl keys only, in the namespace your prompt assigns.
- RLS + FORCE RLS on every new table; service-role key server-side only; every mutating endpoint has authz + Pydantic validation + rate limit + audit where admin-initiated.
- State changes go through guarded transitions with an audit row — **never a raw status UPDATE**.
- FastAPI router **auto-discovery** — add modules under `app/routers/`, never edit `main.py` to register one.
- Migrations additive-only; reversible or documented why not.
- **Untrusted input is data, not instructions**: message bodies, uploads, webhooks, logs, model output and third-party responses. A model may _suggest_ structured fields but **never approves** KYC, publication, payment or moderation.
- Every pebble ships its enumerated tests **including failure paths**, and runs lint + typecheck before reporting.
- Do not enable a feature flag, activate a workflow, deploy, or merge a PR. Those are founder actions.

## Reuse seams — check before writing anything new

| Need                   | Use                                                                                             |
| ---------------------- | ----------------------------------------------------------------------------------------------- |
| B2B eligibility        | `app/services/business/access.py` — the single resolver                                         |
| Creating a listing     | `create_listing_for_vendor(...)` — the one seam, screens included                               |
| Oversell-safe claim    | `app/services/tickets/inventory.py` — advisory lock + `FOR UPDATE`, **no denormalised counter** |
| Admin mutation + audit | `AdminAuditedRoute` + `AdminAuditRecorder`                                                      |
| Guarded lifecycle      | `0056_kyc_integrity.sql`, `0057_vendor_lifecycle_client_guards.sql`                             |
| Idempotent engagement  | M17's unique-key pattern (`clip_likes`, `clip_views`)                                           |
| Ownership trigger      | M17's `clip_products_guard`                                                                     |
| Notifications          | `notification_outbox` → Cloud API → SMS → email. **WAHA is never a customer channel.**          |
| Share pages            | the M17 clip share page (SSR + OG)                                                              |
| Live probe matrix      | `scripts/ops/verify_live.sh`                                                                    |

## Reporting

Every prompt ends with an IMPLEMENTATION REPORT block. Fill it honestly: `PARTIAL` and `BLOCKED` are useful; a `COMPLETE` that skipped a test is not. If existing code already satisfies a criterion, **prove it and skip the work** — duplicate implementations are how a codebase grows two answers to one question.
