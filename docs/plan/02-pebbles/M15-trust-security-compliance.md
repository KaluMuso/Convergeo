# M15 — Trust, Security, Compliance & Legal — Pebbles

9 pebbles. P06 (legal pages) starts early — independent of code. The hardening passes (P03–P05) run late against the near-final surface. Owns i18n namespace `legal`.

---

### M15-P01 — Reviews: submission & vendor replies `M`
**Deps:** M03-P06, M09-P06 · **Files:** `services/api/app/routers/reviews.py` (create: **verified-purchase enforced by order_item link + delivered state**; 1–5★ + text + ≤3 photos public bucket; one per order_item; edit window 7d), `apps/customer/app/[locale]/(shop)/p/[slug]/_components/reviews-section.tsx` (list, photo lightbox, write flow entry), review prompt on order page `account/orders/[id]/_components/review-prompt.tsx`, vendor reply `apps/vendor/app/reviews/page.tsx`
Vendor replies (one per review, edit 24h); review visible immediately (post-moderation via flags M13-P04).
**AC:** non-purchaser cannot submit (API + RLS); photos via CloudinaryImage; reply threading correct.
**Tests:** verified-purchase gate, one-per-item, edit windows, reply authz.

### M15-P02 — Review aggregation & moderation surface `M`
**Deps:** P01 · **Files:** `services/api/app/services/reviews/aggregate.py` (**Bayesian average**: prior m=platform mean, C=confidence weight config; per listing + per vendor; nightly recompute + incremental on write), report flow `(shop)/p/[slug]/_components/report-review.tsx`, aggregates surfaced into cards/search boost (`search_documents.boost_signals` sync)
Bayesian prevents 1-review-5-star gaming; report → flags queue (M13-P04).
**AC:** aggregate matches formula goldens; card stars = aggregate everywhere (single source); report lands in admin queue.
**Tests:** Bayesian goldens (0, 1, many reviews), incremental vs nightly consistency, boost sync.

### M15-P03 — Security headers & CSP `M`
**Deps:** M01-P07, apps stable · **Files:** `infra/Caddyfile` (headers for API+vendor+admin origins), `apps/customer/next.config.ts` + `apps/vendor/next.config.ts` + `apps/admin/next.config.ts` (CSP w/ nonce, HSTS, frame-ancestors, referrer-policy, permissions-policy), `docs/ops/security-headers.md`, CI header-check script `scripts/ci/check-headers.mjs`
CSP allows: self, Cloudinary, Supabase, Lenco widget (customer checkout route only — scoped CSP), GA4; report-only rollout → enforce; admin strictest.
**AC:** Mozilla Observatory A on all origins (staging); Lenco widget works under CSP; zero console CSP violations on E2E paths.
**Tests:** header presence CI check per origin, CSP violation smoke on critical flows.

### M15-P04 — Rate-limit sweep & input fuzz `L`
**Deps:** M04-P07, all routers merged · **Files:** `services/api/app/core/ratelimit_policies.py` (**central policy registry: every mutating route MUST declare a limit — startup assert fails on unregistered mutating route**), `services/api/tests/test_ratelimit_sweep.py`, `services/api/tests/fuzz/test_input_fuzz.py` (schemathesis/hypothesis over OpenAPI: type confusion, huge payloads, unicode, negative/overflow ints on money fields)
The startup assert makes the sweep permanent, not a one-time audit; fuzz runs nightly in CI (fast subset per-PR).
**AC:** unregistered mutating route fails app start (tested); fuzz finds zero 500s (all → 4xx envelopes); money fields reject overflow/negative per schema.
**Tests:** the sweep assert, fuzz suite, limit behavior per policy class (auth/money/write/read).

### M15-P05 — OWASP audit, pen-test-lite & CI security gates `L`
**Deps:** P03, P04 · **Files:** `docs/ops/owasp-audit.md` (Top-10 checklist vs codebase: each item → evidence links to code/tests, or finding + fix prompt reference), `scripts/security/pentest-lite.sh` (authz-matrix probe: every route × role from OpenAPI; IDOR probes on id params; SSRF/redirect checks), `.github/workflows/ci.yml` (add: pip-audit/pnpm audit fail-on-high, gitleaks already M01 — verify, zap-baseline optional job), `services/api/tests/test_authz_matrix.py`
Audit is evidence-based (no checkbox theater); pentest-lite runs against staging on demand + pre-launch.
**AC:** M15 success criterion: zero criticals on checklist (or fixed); authz matrix covers 100% of routes (generated from OpenAPI, unlisted = fail); IDOR probes all denied.
**Tests:** generated authz matrix, pentest script assertions, CI gate behavior.

### M15-P06 — Legal pages `M`
**Deps:** M02-P02 · **Files:** `apps/customer/app/[locale]/(marketing)/legal/terms/page.tsx`, `legal/privacy/page.tsx` (Zambia DPA: consent, retention table, export/delete rights → M04-P06 flows), `legal/returns/page.tsx` (D17 two lanes, plain language), `legal/vendor-agreement/page.tsx` (commissions table from config, payout terms D5, prohibited items D8), `packages/i18n/messages/en/legal.json`, footer component `packages/ui/src/footer.tsx` (links), checkout consent already M07-P05 (links here)
Content drafted from decisions (counsel review = F4 gate before real money — pages marked "last updated"); readable at 360px, anchor-linked sections.
**AC:** M15 success criterion: linked from all app footers + checkout consent; vendor agreement commission table reads config; DPA rights link to working flows.
**Tests:** link integrity, config-driven table, i18n completeness of legal namespace.

### M15-P07 — ZRA invoicing surfaces & VSDC seam `M`
**Deps:** M08-P12 · **Files:** `services/api/app/services/invoicing/pdf.py` (tax-invoice + receipt PDF: sequential no, TPIN fields, Turnover-Tax posture, **VAT-flag-aware layout — off at launch**), `app/routers/invoices.py` (customer/vendor signed download), `app/services/invoicing/vsdc_stub.py` (**Smart Invoice VSDC API seam: interface + stub + activation doc**), `docs/ops/zra-readiness.md` (thresholds K800k/12mo, activation runbook), invoice link wiring in `account/orders/[id]/` (replaces M09-P05 stub)
PDF light (<50KB), ZRA-required fields present, sequence from M08-P12 counters.
**AC:** M15 success criterion (with M08-P12): gapless numbering surfaced on PDFs; VAT-off invoice compliant; VSDC activation = config + implement-one-interface (documented).
**Tests:** PDF field completeness, VAT flag branches, download authz, seam contract test.

### M15-P08 — Prohibited-category enforcement `S`
**Deps:** M03-P07, M12-P03 · **Files:** `services/api/app/services/moderation/prohibited.py` (category-level block from config + **keyword screen on titles/descriptions**: salaula, used phones, alcohol, pharma, live animals, cement/heavy aggregates per D8/G-fence), enforcement hooks in listing create/edit + CSV import paths (dependency injection — no shared-file edits), `services/api/tests/test_prohibited.py`
Server-side block (client hints too) + flag to admin queue on attempts; keyword list config-editable.
**AC:** M15 success criterion: prohibited listing attempt blocked server-side (all three creation paths incl. CSV); evasion basics caught ("salaula" in description); admin sees attempts.
**Tests:** per-path enforcement, keyword fixtures, false-positive guard ("phone case" ≠ "used phone").

### M15-P09 — Backup restore drill & DR runbook `M`
**Deps:** M01-P07 · **Files:** `docs/ops/runbook-disaster-recovery.md` (scenarios: DB loss, OCI VM loss, Supabase outage, Vercel outage, Lenco outage — RTO/RPO per scenario, exact commands), `scripts/ops/restore-staging.sh` (dump → fresh staging restore + smoke verify), drill transcript `docs/ops/drill-log.md`
The drill is the deliverable: actually restore staging from a nightly dump and record timings.
**AC:** M15 success criterion: staging restored from backup ≤30min (transcript proves it); every scenario has commands not prose; Lenco-outage degraded-mode behavior defined (COD/pickup continue).
**Tests:** restore script smoke assertions (row counts, migrations current), runbook link/command validity check.
