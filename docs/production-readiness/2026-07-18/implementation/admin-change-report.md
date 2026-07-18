# Admin panel change report — 2026-07-18

**Branch:** `cursor/panel-admin-a191`  
**Scope:** `apps/admin/**`, `packages/i18n/messages/{en,fr,zh}/admin.json`, this report  
**Out of scope (honoured):** database schema, auth/RLS, production data, payment configuration, deployment, fabricated RBAC/analytics/settlement UI

## Backlog items addressed

| ID              | Pri   | Status in this PR               | Notes                                                                                                                       |
| --------------- | ----- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| ADM-06 / A-04   | P1    | **Done (UI honesty)**           | Empty/zero traffic banner; per-tile empty copy; reconciliation “no report” ≠ Balanced; AI meter dependency called out       |
| ADM-07 / A-05   | P1    | **Done**                        | Dispatch UX reframed to D16 manual book+paste; default courier `other`; explicit confirmation; no Yango CTA framing         |
| ADM-08 / A-06   | P1    | **Partial (read-only honesty)** | Escrow amount default removed; ledger summary from live order rows; MR-B01/MR-W01 dependency labelled. No invented balances |
| ADM-04 / A-03   | P1    | **Partial (empty-state)**       | Duplicate queue empty/permission states document live merge-only API scope                                                  |
| ADM-01 / ADM-02 | P0    | **Not implemented**             | Founder decision + role CRUD API/hook required — must not fabricate user/role management                                    |
| ADM-03          | P0    | **Deferred**                    | KYC UI already calls guarded transitions only; seed/tier integrity is API/ops (I-13)                                        |
| ADM-05 / ADM-09 | P1/P2 | **Deferred**                    | Flag queue / config editors already exist; no contract gap closed here                                                      |

## Live API contracts consumed (unchanged)

- `GET /admin/dashboard` — aggregates; zeros are real; reconciliation may return `status=green` with null report (UI now maps to **unknown**)
- `POST /admin/orders/{id}/dispatch` — courier enum `yango|indrive|other` + tracking note (label only; no courier API)
- `POST /admin/orders/{id}/escrow` — manual hold/release with `MANUAL ESCROW` confirmation phrase
- `GET /admin/orders/{id}` — ledger rows for read-only summary
- `GET /admin/products/duplicates` + `POST /admin/products/merge` — merge only (no reject endpoint)

## UX states shipped

| Surface               | Loading        | Error               | Empty                                 | Confirmation              | Permission denied |
| --------------------- | -------------- | ------------------- | ------------------------------------- | ------------------------- | ----------------- |
| Dashboard             | ✓              | ✓ + dependency hint | ✓ traffic-empty banner + tile empties | n/a                       | ✓ 401/403         |
| Dispatch              | submit spinner | ✓                   | n/a                                   | ✓ manual-booking checkbox | ✓                 |
| Escrow                | submit spinner | ✓ + phrase mismatch | ✓ ledger empty                        | ✓ exact phrase            | ✓                 |
| Moderation duplicates | ✓              | ✓                   | ✓ + API scope note                    | merge dialog (existing)   | ✓                 |

## Security / auditability

- Sensitive mutations still hit audited admin API routes (`require_role("admin")`); UI adds explicit confirmation for dispatch and keeps dual-note escrow confirmation.
- No customer PII expansion; order detail still shows only fields returned by the admin order contract.
- No secrets, payment credentials, or cross-tenant admin surfaces added.
- Role grant/revoke UI **not** added (would fabricate against missing contracts).

## Tests added

- `apps/admin/app/[locale]/_components/dashboard-truth.test.ts`
- `apps/admin/app/[locale]/_components/admin-request.test.ts`
- `apps/admin/app/[locale]/orders/_components/dispatch-model.test.ts`
- `apps/admin/app/[locale]/orders/_components/ledger-summary.test.ts`

## Release impact

- **Risk:** Low — admin UX honesty + confirmation only; no schema/API/deploy changes.
- **Go-live:** Does **not** flip any P0 release gate alone (ADM-01 RBAC decision, KYC integrity, ledger/release still open).
- **Ops:** After deploy of admin app, Access-authenticated admins should see honest empty dashboard when traffic/ledger are zero; dispatch no longer defaults to Yango.

## Verification results (this branch)

| Check                           | Result                          |
| ------------------------------- | ------------------------------- |
| `pnpm --filter admin lint`      | PASS                            |
| `pnpm --filter admin typecheck` | PASS                            |
| `pnpm --filter admin test`      | PASS — 7 files / 36 tests       |
| `pnpm --filter admin build`     | PASS — Next.js production build |

```bash
pnpm --filter admin lint
pnpm --filter admin typecheck
pnpm --filter admin test
pnpm --filter admin build
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
```
