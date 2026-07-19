# Live Beta Release Plan — 2026-07-19

## Goal

Make the **live** Convergeo / Vergeo5 platform useful, polished, trustworthy, and engaging for a **controlled customer beta**, without staging provisioning and without weakening production safety.

## Non-negotiables

- No direct production database edits.
- No real prepaid card/MoMo enablement without deployed accounting + live reconciliation evidence.
- No fake payment success, analytics, KYC verification, vendor capability, or delivery claims.
- No exposure of service-role keys, secrets, PII, or internal ops data.
- Do **not** apply migration `0056` or deploy API changes to production in this program’s Wave 1.
- Verify via local builds + **Vercel Preview** before proposing production frontend rollout.
- One focused PR per wave — no giant all-in-one PR.

## Waves

### Wave 1 — Customer discovery + honesty + fail-closed (this PR)

**In scope**

- Customer: categories already fixed on master — verify on Preview; mobile categories nav; cart badge; PLP/search empty≠unavailable; conversion-path API fail-closed; product-card null-slug; PDP loading/error copy; i18n honesty (verified/near-you/suggestions) en/fr/zh.
- Vendor: shared `resolveApiBaseUrl` + replace localhost fallbacks.
- Admin: Moderation/Config hub pages; shared fail-closed API base.
- Docs: audit, backlog, release plan, wave-1 report.

**Out of scope**

- Production deploy (ops checklist only).
- `0056`, payment enablement, n8n money workflows, staging plane, wishlist/RBAC.

**Exit criteria**

- Lint/typecheck/tests/build pass for affected apps.
- Preview: `/en|/fr|/zh/categories` → **200** (populated / empty / unavailable — not 500).
- No localhost URLs or secrets in Preview HTML.
- Draft PR with Wave 2 split recommended.

### Wave 2 — Independent follow-ons (separate PRs)

| Track          | Tasks                                                                                                                                                                                                   | PR style                         |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| **Customer**   | CUST-01 env verify after founder sets vendor URL; storefront badge honesty post-API; cart free-delivery honesty; optional `/privacy` redirects; search intermittent-500 investigation with runtime logs | `cursor/live-beta-w2-customer-*` |
| **Vendor**     | Services/jobs/returns/disputes/reviews EmptyState+ErrorState parity; listings pause-from-list clarity                                                                                                   | `cursor/live-beta-w2-vendor-*`   |
| **Admin**      | Permission-denied parity on KYC/disputes/flags/business/support; empty-vs-error queue copy                                                                                                              | `cursor/live-beta-w2-admin-*`    |
| **Operations** | Promote Wave 1 to production; re-probe categories; set vendor URL; Sentry DSNs; uptime monitors; backup proof; **do not** apply `0056` until FD-12 + staging drill                                      | Ops runbook / checklists         |

### Wave 3+ — Gates (not frontend polish)

Staging money S1–S6, `0056` apply order, n8n release/tickets, legal FD-08, `public_launch` FD-11 — per `release-gates.md`.

## Production rollout checklist (frontend Wave 1 only)

1. Merge Wave 1 draft PR after Preview sign-off.
2. Confirm Vercel `convergeo-customer` production deploy SHA **≥** categories fix (`b17c311` / tip containing Wave 1).
3. Probe `en`/`fr`/`zh` `/categories` → 200; no digest `3012388270`.
4. Probe homepage, PLP, PDP, search, cart, sell — no localhost; honest unavailable states.
5. Confirm vendor/admin Preview or production deploys include fail-closed API base.
6. **Do not** flip money flags or `public_launch`.
7. **Do not** apply `0056` in this rollout.
8. File post-deploy note under `docs/production-readiness/2026-07-19/production/`.

## Success metric for controlled beta

Invitees can discover categories and products on mobile, understand escrow as a product promise (not a fake live status), add to cart without “coming soon” lies, and never see payment success without ledger confirmation.
