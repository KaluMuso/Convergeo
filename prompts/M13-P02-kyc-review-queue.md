> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free.

# M13-P02 — KYC review queue

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- **Admin base is merged (M13-P01):** `services/api/app/routers/admin_base.py` (mount your router on it → `require_role('admin')` + transparent `audit_log` automatic); admin app `[locale]/layout.tsx` + gated middleware. Admin app `localePrefix:"always"` → pages at **`apps/admin/app/[locale]/kyc/`**.
- **KYC backend is merged (M12-P02):** `app/services/kyc/state_machine.py` has `KycStateMachine`, `transition_*`, `KycApplicationStatus (draft|submitted|approved|rejected)`; `kyc_records` (`vendor_id`, `status`, `momo_name_match jsonb`, `reviewer_notes`, `doc_storage_paths`); `vendors.status`/`kyc_tier` server-controlled (service-role writes). **Your decisions drive that state machine** (approve → vendor active; reject/resubmit) + write an `audit_log` row + enqueue a **`notification_outbox`** row (M14-P01 dispatcher sends it).
- **⚠ Interface edge with M12-P02b (parallel):** KYC docs live in a **private `kyc-docs` Storage bucket** created by M12-P02b (running in parallel). Your doc viewer needs **short-lived signed DOWNLOAD URLs (≤5 min)** for those paths. Build the download-signing against `service_client.client.storage.from_("kyc-docs").create_signed_url(path, 300)`; if M12-P02b hasn't merged when you branch, gate the viewer behind a documented stub + note the dependency (do not hardcode a bucket that doesn't exist yet — read the bucket name from a constant).
- i18n: `admin` namespace registered; `admin.json` exists (M13-P01/P07). **You add a nested `kyc` section** (no flat dotted keys). Only W7 pebble touching `admin.json`.
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P02.

## 2. Objective & scope

Admin KYC queue (oldest-first, SLA badge) + review detail (docs viewer via short-lived signed URLs, NRC/selfie side-by-side, momo name-match result, approve / reject-with-reason-template / request-resubmit) driving the M12-P02 state machine + vendor notification.
**Non-goals:** no KYC backend/state machine (M12-P02 — you call it), no signing endpoint for uploads (M12-P02b), no other admin queues.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/kyc/page.tsx` (queue) · `kyc/[id]/page.tsx` (review detail) · `kyc/_components/*` · `services/api/app/routers/admin_kyc.py` (mounted on `admin_base`: list queue, get detail + signed doc URLs, decision endpoints) · `services/api/tests/test_admin_kyc.py`
- **Modify:** `packages/i18n/messages/en/admin.json` (add nested `kyc` section)
  **Guardrail: nothing else. Do NOT edit `admin_base.py`/layout/middleware (M13-P01), `kyc.py`/`state_machine.py` (M12-P02 — call, don't edit), `main.py`, schema/db.ts, or other namespaces.**

## 4. Implementation spec

- **`admin_kyc.py`** (on `admin_base` → admin-only + audited): `GET /admin/kyc` (queue: submitted records **oldest-first**, with an **SLA badge** field computed from `updated_at`); `GET /admin/kyc/{id}` (detail + **short-lived signed download URLs (≤5 min)** for `doc_storage_paths`, momo name-match result, vendor context); **decision endpoints** — `approve`, `reject` (reason template + free-text), `request-resubmit` — each calls the **M12-P02 state machine** (→ `vendors.status`/`kyc_tier` via service-role), and **enqueues a `notification_outbox` row** for the vendor (dedupe_key per M14-P01). Every decision is audited (automatic via `admin_base`).
- **Pages:** queue (oldest-first + SLA badge); detail (NRC/selfie **side-by-side** via signed URLs, name-match result, approve / reject-with-template / resubmit). Signed URLs **unusable after expiry**. Copy via `admin.kyc.*`.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Admin `noindex`. **Security:** admin-only (admin_base); **signed doc URLs expire ≤5 min** (tested); decisions audited + notified; state writes via M12-P02 service-role path (no raw status UPDATE); private bucket never public.

## 10. Tests (RUN before reporting)

`test_admin_kyc.py`: **signed-URL expiry** (URL unusable after TTL / TTL ≤300s asserted); **decision → state transition + notification_outbox row** (approve → vendor active + outbox enqueued; reject/resubmit); **queue ordering (oldest-first) + SLA badge**; non-admin → 403 (via admin_base). i18n completeness `admin.kyc.*`. `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`; `uv run pytest`, `ruff`, `mypy`.

## 11. Acceptance criteria / DoD

- [ ] End-to-end: submission → review → approve → vendor live; doc URLs unusable after expiry (≤5 min).
- [ ] Every decision drives the M12-P02 state machine + audited + vendor-notified (outbox).
- [ ] Queue oldest-first + SLA; non-admin 403; `admin.kyc.*` nested; repo + API green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M13-P02 — KYC review queue
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none") — note M12-P02b bucket dependency status
**TESTS:** paste signed-URL-expiry + decision→state+notification + queue-order output
**EXCERPTS:** the decision→state-machine+outbox handler — nothing else
**QUESTIONS:** (or "none")
