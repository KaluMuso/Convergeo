# M13 — Admin App & Merchandising — Pebbles

11 pebbles. Hardened separate origin; **every mutation writes `audit_log` (who/what/before/after)** via shared middleware from P01. Scope fence: queues + config + dashboards only — anything else goes to n8n or post-launch. Owns i18n namespace `admin`.

---

### M13-P01 — Admin hardening & shell `M`
**Deps:** M04-P02/P03, M01-P05 · **Files:** `apps/admin/app/layout.tsx` (nav shell), `apps/admin/middleware.ts` (admin role + Cloudflare Access JWT assertion in prod), `services/api/app/core/admin_audit.py` (**audit middleware: every admin-role mutation → audit_log with before/after diff**), `app/routers/admin_base.py`, `infra/Caddyfile` (admin vhost: IP allowlist + CF Access — **only this pebble touches Caddyfile this wave**), `docs/ops/admin-access.md`
Separate origin (admin.vergeo5.com), noindex, no public assets; audit middleware is transparent (routers opt-out impossible for mutations).
**AC:** non-admin JWT → 403 before any handler; mutation without audit row impossible (test hooks); prod access requires CF Access header (bypass flag only non-prod).
**Tests:** authz gates, audit completeness (a mutation missing audit fails test), allowlist config validation.

### M13-P02 — KYC review queue `M`
**Deps:** P01, M12-P02 · **Files:** `apps/admin/app/kyc/page.tsx` (queue: oldest-first, SLA badge), `kyc/[id]/page.tsx` (**docs viewer via short-lived signed URLs** from private bucket, NRC/selfie side-by-side, momo name-match result, approve / reject-with-reason-template / request-resubmit), `services/api/app/routers/admin_kyc.py`, `packages/i18n/messages/en/admin.json`
Decisions drive M12-P02 state machine + vendor notification (outbox); signed URLs expire ≤5min; rejection reasons templated + free-text.
**AC:** end-to-end: submission → review → approve → vendor live; doc URLs unusable after expiry; every decision audited + notified.
**Tests:** signed-URL expiry, decision→state+notification, queue ordering/SLA.

### M13-P03 — Canonical-product moderation & dupe detection `M`
**Deps:** P01, M03-P02 · **Files:** `apps/admin/app/moderation/products/page.tsx` (pending canonicals; **dupe suggestions via trgm similarity + same-category**; approve/edit/merge-into-existing/reject), `services/api/app/routers/admin_products.py` (+merge: listings re-point, old slug 301, aliases union), `services/api/tests/test_product_merge.py`
Merge is the delicate op: listings re-pointed atomically, search projection resynced, redirects kept.
**AC:** merge moves all listings + reviews aggregate correctly; dupe suggestions catch fixture near-dupes ("Itel A70" vs "itel A-70"); rejected canonical notifies vendor with reason.
**Tests:** merge atomicity + redirect, dupe scoring fixtures, projection resync.

### M13-P04 — Listing & review flag queues `M`
**Deps:** P01, M03-P06 · **Files:** `apps/admin/app/moderation/flags/page.tsx` (unified queue: listing flags, review flags; actions: dismiss / unpublish / remove / warn-vendor / escalate-suspend), `services/api/app/routers/admin_flags.py`
Prohibited-category attempts land here too (server blocks + flags per M15-P08); repeat-offender counter per vendor; suspension = vendor status change (listings hidden, payouts continue for delivered orders).
**AC:** unpublish reflects publicly ≤1min; suspension semantics exact (in-flight orders unaffected); all actions audited + notified.
**Tests:** action semantics matrix, suspension side-effects, repeat-counter.

### M13-P05 — Disputes console `M`
**Deps:** P01, M09-P09, M08-P10 · **Files:** `apps/admin/app/disputes/page.tsx` (queue by age/value), `disputes/[id]/page.tsx` (both-side evidence viewer signed URLs, order+payment+ledger context panel, decisions: **full refund / partial (amount ngwee) / release to vendor** with mandatory note), `services/api/app/routers/admin_disputes.py`
Decisions execute M08 services (refund/release) — never manual ledger pokes; partial refund validated ≤ order total.
**AC:** each decision produces exactly the right ledger transactions; note mandatory; parties notified; dispute SLA visible.
**Tests:** decision→ledger mapping per type, partial bounds, double-decision guard.

### M13-P06 — Order ops console & manual dispatch `L`
**Deps:** P01, M09-P01/P10 · **Files:** `apps/admin/app/orders/page.tsx` (search ANY order: id/phone/vendor/status), `orders/[id]/page.tsx` (full context: items, payment, ledger, timeline; **manual dispatch panel: courier booked (Yango/inDrive/other) + tracking note + status updates**; status intervention via state machine with reason; **escrow manual hold/release with dual-note** — reason + confirmation phrase), `services/api/app/routers/admin_orders.py`
Manual dispatch drives M09-P10 customer timeline; interventions are state-machine transitions (audited), never raw updates; escrow manual ops post via M08 templates with `manual` flag + both notes.
**AC:** dispatch entry visible to customer ≤1min; illegal intervention transitions rejected; manual escrow op requires dual-note (enforced) and balances.
**Tests:** search correctness, dispatch→timeline, dual-note enforcement, manual-op ledger balance.

### M13-P07 — Config editors `L`
**Deps:** P01, M03-P07 · **Files:** `apps/admin/app/config/` (`commissions/page.tsx`, `delivery-zones/page.tsx`, `platform/page.tsx` COD cap/quotas/AI caps/release windows, `flags/page.tsx`, `categories/page.tsx` tree editor w/ drag-reorder + prohibit toggle), `services/api/app/routers/admin_config.py` (typed validation per key: bps 0–2000, ngwee ints, window hours bounds)
Every config mutation validated + audited + effective without deploy; category tree edits guard against orphaning (move-children prompt); dangerous edits (COD cap, commissions) show confirmation with old→new diff.
**AC:** commission change affects only NEW orders (snapshots immune — cross-test with M08-P12); zone fee change live ≤1min; invalid values rejected with field errors.
**Tests:** validation bounds per key, tree integrity ops, snapshot-immunity integration, audit diff.

### M13-P08 — Merchandising manager `L`
**Deps:** P01, M03-P07, M05-P01 · **Files:** `apps/admin/app/merch/page.tsx` (slot board: hero/banners/collections/events-row order), `merch/_components/` (**hero variant library picker** — variants from design set, preview thumbnails; banner slot editor w/ Cloudinary image + link + schedule from/to; **featured-collection builder**: pick listings/category/tag query, order, title i18n keys; rotation scheduling), `services/api/app/routers/admin_merch.py`, preview mode (`?merch_preview=draft` token-gated on customer home)
The founder's admin-swappable elements (M13 charter): compose home without deploys; draft→publish; schedule windows (Africa/Lusaka).
**AC:** M13 success criterion: swap hero / reorder collections → customer home ≤1min without deploy; expired schedule auto-falls-back; preview shows draft without publishing.
**Tests:** slot CRUD + schedule windows, publish/draft isolation, fallback on empty/expired, preview token gate.

### M13-P09 — Dashboards `M`
**Deps:** P01, M08-P07, M06-P06 · **Files:** `apps/admin/app/page.tsx` (admin home = dashboard: **GMV, orders by status, payout liabilities (ledger), reconciliation status w/ mismatch alert, vendor/listing/product counts, AI usage + spend vs $15 cap**, funnel snapshot), `services/api/app/routers/admin_dashboards.py` (aggregate endpoints, cached 5min)
Reconciliation tile surfaces M08-P07 daily report state (green/red + drill-in); payout liabilities = escrow + released-unpaid from ledger.
**AC:** M13 success criterion: injected ledger mismatch flags red on dashboard; numbers reconcile with source tables; loads <2s.
**Tests:** aggregate correctness vs fixtures, mismatch surfacing, cache behavior.

### M13-P10 — Support inbox-lite `M`
**Deps:** P01, M13-P06 · **Files:** `apps/admin/app/support/page.tsx` (order/customer lookup by phone/id; context card; **canned replies (i18n-keyed templates) sent via WhatsApp/SMS through outbox**; interaction log per customer), `services/api/app/routers/admin_support.py`, canned templates `packages/i18n/messages/en/admin.json` (support section — same file as P02: **different wave**)
Not a ticketing system (scope fence): lookup + canned outbound + log; free-text send allowed with audit.
**AC:** lookup by partial phone works; canned send lands in outbox with correct channel fallback; log complete.
**Tests:** lookup matching, outbox payloads, audit of sends.

### M13-P11 — n8n admin hooks & daily digest `S`
**Deps:** P09, M14-P06 · **Files:** `infra/n8n/admin-digest.json` (daily founder digest: GMV, orders, payouts due, reconciliation status, KYC queue depth, flags pending — via WhatsApp/email), `services/api/app/routers/internal_digest.py` (digest data endpoint, internal-token), `docs/ops/n8n-workflows.md` (registry of all n8n workflows + import/export procedure)
Digest = the founder's morning coffee view; doc consolidates every n8n workflow shipped across mountains (backup, sweepers, reconciliation, jobs, digest) with ownership + schedule table.
**AC:** digest arrives with real numbers matching dashboard; workflow registry complete (CI check: every `infra/n8n/*.json` listed).
**Tests:** digest data endpoint correctness + auth, registry completeness script.
