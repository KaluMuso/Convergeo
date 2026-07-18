# Missing & Conflicting Items — Convergeo 60-Day Development Roadmap

**Audit date:** 2026-07-18 · Categorized per the audit contract. Each item cites the fact ID from `extracted-facts.json` and the foundation risk (R#) where applicable.

> **Framing.** This document is a rank-4 *plan at 0% completion*. It does not assert that anything is deployed. "Missing" below means **the plan's intended end-state / launch gate is not met in production**, verified by an appropriate scoped lookup (or explicitly marked as access-limited). Stack "conflicts" are largely **superseded decisions** (D18–D24), flagged so no one treats the roadmap as the live architecture.

---

## a. Missing production records

*(Expected operational data that the plan's launch state implies should exist, confirmed absent by foundation aggregates — not by guessed table names.)*

| Fact | Record class | Expected table (established) | Live count | Evidence | Note |
| --- | --- | --- | --- | --- | --- |
| F048 | Verified real payment | `payments` | **0** | foundation DB aggregate | Launch gate "small real transaction" unmet; **P0** |
| F025 | Escrow/charge ledger postings | `ledger_transactions`/`ledger_postings` | **0** | foundation | No money has moved through the ledger; **P0 (R2)** |
| F050 | Real (non-demo) catalogue | `vendors`/`vendor_listings`/`listing_images` | 3 demo / 134 / 134 `demo/` | foundation (R5) | Marketplace is seed data, not real vendors |
| F016 | KYC records | `kyc_records` | **0** | foundation | Vendor KYC lifecycle never exercised |
| F028 | Orders | `orders` | **0** | foundation | No purchase has completed |
| F031 | Reviews | `reviews`/`review_aggregates` | **0** | foundation | Verified-purchase review path unused |
| F038 | Disputes / refunds | `disputes`/`refunds`/`returns` | **0** | foundation | Dispute/refund lifecycle unexercised |
| F035 | Analytics / funnel events | `analytics_events`/`funnel_events` | **0** | foundation (R4) | Admin dashboards have no data to show |

> These are **expected-empty for a demo environment**. They become blockers only against the plan's "CONVERGEO IS LIVE / real transaction" launch state. **Do not seed** — remediation is a controlled sandbox/first-real-transaction, not record creation.

---

## b. Missing fields / schema support

*(Schema elements the document requires that are absent on live per foundation drift analysis.)*

| Fact | Required by doc | Expected object | Live status | Evidence | Impact |
| --- | --- | --- | --- | --- | --- |
| F033 | `superadmin` / `moderator` admin roles | `user_roles.role` CHECK values | **Absent** — CHECK is `('customer','vendor','admin')` only | repo `0002_identity_vendors.sql`; 0 superadmin refs | **P0** two-tier admin RBAC unsupported |
| F014 | Custom access-token role claim | `custom_access_token*` fn (migration `0051`) | **Not applied on live** | foundation access-inventory §3.5 | Role provisioning manual; JWT role claims lag |
| F051 | (context) translation overrides / service-bookable | `translation_overrides` (0053), `services.bookable` (0055) | **Missing on live** (repo has them) | foundation schema-inventory §2 | Migration drift repo→live (not a doc requirement, noted for parity) |

> No schema field was declared missing on a guessed table; each maps to an established table/migration in the foundation inventory.

---

## c. Configuration / workflow gaps

| Fact | Required by doc | Expected config/workflow | Live status | Evidence | Impact |
| --- | --- | --- | --- | --- | --- |
| F025 | Escrow auto-release on delivery/QR | n8n `release-job` + `post_transaction` ledger hook | **Not deployed** (only 2 workflows live) + **code hook missing** | n8n VERIFIED this session; R2 | **P0** escrow never auto-releases; ledger never posts on prepaid success |
| F042 | Vendor onboarding, abandoned-cart, review-request automations | n8n workflows (JSON in repo) | **Authored, not live** | 18 JSONs in repo; 2 active live | Lifecycle automation inactive (R3) |
| F049 | DB backup scheduled + first backup done | n8n backup workflow / OCI cron | **Absent** (only `backup-schedule.md`) | foundation R3 | Backup RPO unproven; **launch gate unmet** |
| F045 | Staging mirrors production | `deploy-staging.yml` | **Stub** | foundation architecture-inventory | No true staging gate |
| F046 | Sentry error tracking + UptimeRobot | Sentry projects + DSNs; UptimeRobot monitors | **No Vergeo5 Sentry projects**; UptimeRobot NOT_AUDITABLE | foundation R4 | Production blind to errors |
| F022/F041 | Blocking CI quality/security gates | GitHub required checks | **Non-blocking** (secret-scan/Lighthouse `continue-on-error`) | foundation R7 | Defects/secrets can merge |
| F026 | Zamtel Kwacha collections | `zamtel_collections` flag / `LENCO_ENABLE_ZAMTEL` | **Disabled** (flag false; payout-only) | foundation flags; repo | **P0** Zamtel checkout unavailable vs plan |
| F015 | OTP rate limiting enforced | `rate_counters` + API limiter | Present but **runtime unverified** | foundation | OTP abuse protection unproven |

---

## d. UI / customer / vendor / admin gaps

| Fact | Required by doc | Surface | Live status | Evidence | Impact |
| --- | --- | --- | --- | --- | --- |
| F021 | Seller onboarding entry from customer site | customer → vendor CTA | **Broken** — CTAs disabled ("vendor signup temporarily unavailable"); `NEXT_PUBLIC_VENDOR_APP_URL` unset | foundation R1 | Cannot acquire sellers from marketing surface |
| F033/F034 | Admin role-management + moderator/superadmin separation | admin app | **No user/role-management UI**; single admin role | foundation R6 | Role grants via manual SQL; no separation of duties |
| F030 | Customer checkout UI (methods, redirect, USSD) | apps/customer checkout | **NOT_AUDITABLE** (behind cart/session); provider mismatch (Lenco not DPO) | egress-limited | Payment UX parity unverified |
| F036/F037 | In-app notifications + preferences; WhatsApp opt-out | customer/vendor | In-app/WebSocket + preference UI **unverified**; 0 live sends | foundation | Notification UX unproven |
| F034 | KYC review + product approval queues | admin app | Behind Cloudflare Access; **not audited**; 0 KYC/audit rows | access-inventory | Moderation flows unproven |

---

## e. Conflicting data

*(Document asserts X; production authoritatively uses Y. Stack conflicts are superseded by locked decisions D18–D24 unless flagged P0.)*

| Fact | Document says | Production reality | Nature | Priority |
| --- | --- | --- | --- | --- |
| F005 | Payment = **DPO Pay** | **Lenco** (70 refs, 0 DPO; D21) | Payment-provider conflict | **P0-investigate** → doc stale |
| F026 | **Zamtel Kwacha** collections at launch | Zamtel payout-only; collections flag OFF | Payment-scope conflict | **P0** |
| F033 | Admin roles **superadmin + moderator** | Single `admin` role only | Admin-RBAC conflict | **P0-investigate** |
| F003 | Backend **Django 5.x + DRF** | **FastAPI** (D18) | Stack conflict (superseded) | P1 |
| F004 | Hosting **Vercel + Railway** | Vercel + **OCI/Hetzner + Supabase + Cloudflare** | Hosting conflict (superseded) | P1 |
| F006 | Search **Meilisearch** | **Postgres FTS + pgvector** (RRF) | Search conflict (superseded) | P1 |
| F014 | JWT **simplejwt** | **Supabase Auth** (+ Google) | Auth conflict (superseded) | P1 |
| F007 | **Redis** cart/cache | Postgres-backed; no Redis | Stack conflict (superseded) | P2 |
| F008 | Async **Celery + Redis** | **n8n + outbox** | Stack conflict (superseded) | P2 |
| F009 | Email **SendGrid/Mailgun** | **Resend** | Provider conflict (superseded) | P2 |
| F010 | Monorepo `*-app/` + `backend/` | `apps/*` + `services/api` + `packages/*` | Layout conflict | P2 |
| F011 | `AI_CONTEXT.md` | `CLAUDE.md` | Convention conflict | P2 |
| F013 | PostgreSQL **16** | PostgreSQL **17.x** | Version conflict | P2 |
| F002 | 60 working days = **8 weeks** | 60 wd ≈ 12 weeks; window elapsed | Schedule conflict (doc-internal) | P2 |
| F050 | "**CONVERGEO IS LIVE**" (real marketplace) | Demo/seed data; `public_launch=false` | State conflict | P1 |
| F001 | Brand "**Convergeo**" | "**Vergeo5**" (vergeo5.com) | Naming conflict | P2 |

---

## f. Access / evidence limitations (this session)

*(Honest declaration per contract §5 / rank hierarchy. These are why some rows are NOT_AUDITABLE or lean on the foundation baseline instead of a fresh probe.)*

| Limitation | Affected facts | Cause | What would resolve it |
| --- | --- | --- | --- |
| Live HTTP to `*.vergeo5.com` blocked | F019, F020(*), F030, F039, F043, F047, F050(*) | Agent egress policy → 403 CONNECT | Allow `www./api./vendor./admin.vergeo5.com` in egress policy, then re-run foundation HTTP pack |
| Supabase live SQL unavailable | all DB-count rows (F016, F018, F023–F038, F048–F050) | Supabase MCP unauthenticated + `mcp.supabase.com` egress-blocked | Authenticate Supabase MCP (interactive `/mcp`) or allow egress; re-run read-only aggregate pack |
| Vercel MCP intermittently disconnected | F020, F021 (deploy detail) | MCP transport dropped mid-session | Not blocking — foundation has VERIFIED Vercel deploy evidence |
| API container git SHA / image digest | F003 (API version parity) | GHCR auth + no host SSH (foundation) | Read `API_IMAGE_TAG`/digest with least privilege |
| Cloudflare Access / SSL Labs / UptimeRobot | F046, F047 | External dashboards not reachable/probed | Read monitor + Access policy state; run SSL Labs |
| Admin/vendor internals behind auth | F030, F034, F036, F037 | Login/Access gates (correctly) block anon audit | Authenticated read-only walkthrough with scoped test accounts |

(*) marked facts have **foundation-baseline** evidence (same audit date) even though not re-probed this session; they are labelled from that baseline, not from a fresh probe.

---

## Summary counts

- Missing production records (demo-expected, launch-gating): **8 classes**
- Missing schema support: **3** (1 P0: admin roles)
- Configuration/workflow gaps: **8** (2 P0: escrow release, Zamtel)
- UI gaps: **5**
- Conflicts: **16** (3 P0: DPO/Lenco, Zamtel, admin RBAC; rest superseded stack or naming/state)
- Access/evidence limitations: **6 classes**
