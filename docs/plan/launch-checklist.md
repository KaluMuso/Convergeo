# Vergeo5 — Go / No-Go Launch Checklist

> **Purpose:** the single gate document for taking Vergeo5 from private beta to
> real-money public launch. Every launch gate is enumerated below with an owner
> and an **evidence slot** (link a PR, test run, dashboard, or document).
>
> **Rule (non-negotiable):** a line may only be checked when its evidence link is
> filled and the owner has verified it. **Founder gates (F1–F9) and the five
> live-execution / staging proofs are left UNCHECKED on purpose** — they cannot be
> satisfied from the build environment (no staging, founder actions outstanding).
> Do not check them to "tidy up" the list; an unchecked founder gate is a hard
> **NO-GO** for real-money launch.
>
> **Beta vs public:** the site ships **invite-only** (feature flag
> `public_launch = false`; the `/beta` gate + `beta_invites` codes). Flipping
> `public_launch` ON in the admin config opens the site to the public **with no
> deploy** — but MUST NOT be flipped until every BLOCKING gate below is green.

Legend: `[x]` done + evidence linked · `[ ]` outstanding · **Owner** in bold ·
_(staging)_ = needs the staging environment · _(founder)_ = founder action.

---

## 0. Launch decision (sign-off — sign LAST)

These lines are the actual go/no-go. They may only be signed when Sections 1–5
are all green. **Leave unchecked until then.**

> **Prompt 12 audit (2026-07-20):** agent recommendation **NO_GO**.  
> Evidence: `docs/production-readiness/2026-07-20/go-no-go-report.md` · gates: `docs/production-readiness/2026-07-18/consolidated/release-gates.md`.  
> Live: API **502**; `public_launch=false`; money tables empty; n8n all inactive; F4/F9b open.  
> **Do not** treat this note as founder sign-off — founder lines below stay unchecked.

- [ ] **GO / NO-GO — Founder** has reviewed Sections 1–5; every BLOCKING gate is green. — **Owner: Founder** — Evidence: _(link decision record; supersede agent NO_GO only with written founder decision)_
- [ ] **Escrow real-money launch approved** — counsel gate **F4** cleared (Section 4). — **Owner: Founder + Counsel** — Evidence: _____
- [ ] **Payments live** — Lenco production credentials in place, sandbox E2E green (**F9**). — **Owner: Founder** — Evidence: _____
- [ ] **`public_launch` flip authorised** — flag flipped ON only after the three lines above are signed. — **Owner: Founder** — Evidence: _(admin audit_log entry)_ — **live flag still false as of 2026-07-20 audit**
- [ ] **Rollback plan acknowledged** — flip `public_launch` OFF + DR runbook (M15-P09) on hand. — **Owner: Founder** — Evidence: `docs/ops/` DR runbook · rollback drill still NOT_RUN (`ops-drills/`)

---

## 1. Mountain success criteria (M01–M16)

Each mountain's Phase-1 success criteria (see `docs/plan/01-mountains.md`). Link
the merged pebble PRs / test runs as evidence. Items whose proof requires the
staging environment or a founder gate are tagged and stay **unchecked**.

- [ ] **M01 — Foundations/Infra:** fresh clone → `pnpm i && pnpm dev` runs all apps; CI green; deploy+rollback demonstrated _(staging)_; no secrets in repo (scanner). — Evidence: CI `JavaScript / TypeScript` (install/build) + `Python API` · `Secret scan (gitleaks)` (all green on master `d91479b`); deploy+rollback stubbed in `.github/workflows/deploy-staging.yml` _(staging — awaits OCI)_
- [ ] **M02 — Design system:** all screens build from the kit; preview renders every component with i18n keys; a11y ≥95; tokens single-source. — Evidence: `scripts/ci/ui-preview-coverage.mjs` (preview coverage gate) · Lighthouse A11y in `Performance budgets` _(a11y ≥95 advisory in CI — confirm on staging build)_
- [ ] **M03 — Data core:** `supabase db reset` clean; **RLS suite proves customer/vendor/admin isolation** (incl. cross-vendor denial); seed browsable; types compile; hot queries use indexes. — Evidence: `services/api/tests/rls/` (`test_matrix.py`, `test_no_untested_tables.py`) · CI `Migration replay (fast)` + `Database / typegen drift` + `RLS isolation matrix` — all green on master `d91479b`
- [ ] **M04 — Auth:** phone-only signup→browse→order; client role-escalation impossible (tested); OTP brute-force blocked (tested); deletion cascades. — Evidence: `services/api/tests/test_identity.py`, `test_auth_dep.py`, `test_ratelimit.py` (OTP brute-force), `test_authz_matrix.py` (role-escalation), `test_account.py` (deletion cascade); full signup→browse→order journey in E2E `Playwright critical paths` _(staging)_
- [ ] **M05 — Catalog/Search:** exact/fuzzy/semantic search relevant on seed; comparison sorts by price/distance; PLP LCP ≤2.5s Fast-3G; rich results validate. — Evidence: `services/api/tests/test_search.py`, `test_catalog.py`, `test_comparison.py`; PLP LCP + rich-results via `Performance budgets` (Lighthouse) _(Fast-3G LCP confirmed on staging build)_
- [ ] **M06 — Ask Vergeo:** 20-Q eval grounded, zero fabricated listings; quota + kill-switch enforced; p95 <6s; cost/answer ≤$0.002. — Evidence: `services/api/tests/evals/` (`test_ask_grounding.py`, `ask_eval_set.yaml`) · CI `Ask Vergeo grounding evals`; quota/kill-switch `test_ask_quota.py`; p95/cost-per-answer measured at runtime _(staging + live key)_
- [ ] **M07 — Cart/Checkout:** two concurrent buyers cannot oversell last unit (race test); guest→auth merge preserves cart; ≤4 steps at 360px; reservation expiry restocks; COD ≤K500 enforced. — Evidence: `services/api/tests/test_order_create_concurrency.py` (oversell race), `test_reservations.py` (expiry restock), `test_cart.py` (guest→auth merge), `test_cod.py` (COD ≤K500); ≤4-step 360px flow in E2E `Playwright critical paths` _(staging)_
- [ ] **M08 — Payments/Escrow:** sandbox E2E charge→webhook→hold→confirm→release→payout for all 3 rails + card _(founder: F9)_; ledger balances (Σ postings = 0); dup/out-of-order/forged webhooks handled; reconciliation matches to the ngwee; every payment endpoint authz + rate-limited. — Evidence: `services/api/tests/test_ledger.py` (Σ postings=0), `test_webhooks.py` + `test_payment_retry.py` (dup/out-of-order/forged), `test_reconcile.py` (to-the-ngwee), `test_payments_card.py`, `test_payouts.py`; authz+rate-limit `test_authz_matrix.py` / `test_ratelimit.py`; sandbox E2E charge→…→payout _(founder: F9)_
- [ ] **M09 — Orders/Fulfilment:** every legal transition tested + illegal rejected; QR verify offline-tolerant + single-use; auto-confirm/release idempotent; refund math exact. — Evidence: `services/api/tests/test_order_state.py` (legal/illegal transitions), `test_ticket_verify.py` (single-use QR), `test_order_confirmation.py` + `test_release.py` (auto-confirm/release idempotent), `test_refund_execute.py` (refund math); offline QR path in E2E _(staging)_
- [ ] **M10 — Events/Ticketing:** create→publish→sell→QR-validates-once (offline incl.)→escrow settles per rule; screenshot QR fails after 60s; oversell impossible at capacity (race test). — Evidence: `services/api/tests/test_organiser_events.py`, `test_ticket_purchase.py`, `test_ticket_inventory.py` (oversell race), `test_ticket_verify.py` + `test_ticket_scan_sync.py` (QR once/offline/dynamic), `test_event_release.py` (escrow per rule); full create→sell→scan E2E _(staging)_
- [ ] **M11 — Services/RFQ:** job→quotes→accept→deposit→complete→balance→review E2E; providers can't see each other's quotes; pre-acceptance contact-strip (tested). — Evidence: `services/api/tests/test_rfq.py`, `test_quotes.py` (quote isolation), `test_contact_strip.py`, `test_service_escrow.py` (deposit/balance), `test_job_completion.py` (review); full E2E job→…→review _(staging)_
- [ ] **M12 — Vendor portal:** unassisted T1 signup→KYC→first listing ≤10min; CSV 100-row mixed-error row feedback; caps enforced server-side; daily-driver one-handed 360px. — Evidence: `services/api/tests/test_csv_import.py` (row-level error feedback), `test_kyc_caps.py` + `test_kyc_archetype.py` (server-side caps), `test_listing_create.py` / `test_listing_manage.py`; ≤10-min unassisted + one-handed 360px _(manual/E2E on staging)_
- [ ] **M13 — Admin/Merch:** every mutation audited (who/what/before/after); merch change reflects on home ≤1min no-deploy; KYC queue end-to-end; reconciliation flags injected mismatch. — Evidence: `services/api/tests/test_admin_audit.py` (who/what/before/after), `test_admin_merch.py`, `test_admin_kyc.py` (KYC queue), `test_reconcile.py` (injected-mismatch flag); merch-reflects-≤1min-no-deploy _(staging)_
- [ ] **M14 — Notifications:** lifecycle fires exactly once per event (dedupe tested); WhatsApp→SMS fallback ≤2min _(founder: F5)_; STOP honored cross-channel; founder digest daily. — Evidence: `services/api/tests/test_dispatcher.py` (once-per-event dedupe), `test_notification_i18n.py`, `test_wa_webhook.py` (STOP cross-channel), `test_fallback.py`, `test_internal_digest.py` (founder digest); WhatsApp→SMS live fallback _(founder: F5)_
- [ ] **M15 — Trust/Security/Compliance/Legal:** OWASP zero criticals; **restore drill ≤30min** _(staging — M15-P09)_; legal pages linked from footers + checkout consent; invoice numbers gapless under concurrency (tested); prohibited-category listing blocked server-side. — Evidence: CI `Dependency audit` + `Security gates (headers + authz matrix)` (OWASP surface) · legal `apps/customer/app/[locale]/(marketing)/legal/` · `services/api/tests/test_commissions_invoicing.py::TestInvoicingGapless` (invoice gapless) · `test_prohibited.py`; restore drill (M15-P09) _(staging)_
- [ ] **M16 — Perf/PWA/Analytics/Launch QA:** all budgets green in CI on launch commit; **E2E green on staging vs Lenco sandbox** _(staging — M16-P07)_; **load p95 <500ms @100cc** _(staging — M16-P08)_; **beta cohort invitable/gated** (this pebble); go/no-go signed (Section 0). — Evidence: `Performance budgets` (bundle/image/Lighthouse) · E2E `Playwright critical paths` _(staging)_ · load test M16-P08 _(staging)_ · beta gate `services/api/tests/test_beta.py`; go/no-go = Section 0

---

## 2. Performance & quality budgets (CI-enforced)

- [ ] Customer routes ≤150KB gz JS on the launch commit. — Evidence: `scripts/ci/bundle-guard.mjs` (Bundle guard step) in `Performance budgets` — green on master; **re-verifies on the launch commit**
- [ ] LCP ≤2.5s Fast-3G / 360px; Lighthouse mobile Perf ≥90 / SEO ≥95 / A11y ≥95. — Evidence: `lighthouserc.json` in `Performance budgets` (Lighthouse CI step) _(advisory in CI — confirm ≥ thresholds on staging build)_
- [x] i18n completeness lint green (no hardcoded strings, no missing keys, no formatK bypass). — Evidence: `scripts/ci/i18n-lint.mjs` — "i18n completeness sweep (blocking)" step in `Performance budgets`, green on master `d91479b`
- [x] Full API suite + typecheck + lint green (`uv run pytest`, `ruff`, `mypy`; turbo `test/lint/typecheck`). — Evidence: CI `Python API` (Ruff + Mypy + Pytest) and `JavaScript / TypeScript` (Lint + Typecheck + Test) — both green on master `d91479b`
- [ ] Observability live: Sentry capturing, error budget 99.5% dashboard _(founder: DSN/UptimeRobot — M16-P06)_. — Evidence: `services/api/tests/test_sentry_scrubber.py` (PII scrub wired); live capture needs founder DSN _(founder)_

---

## 3. Staging-gated live-execution proofs (all UNCHECKED — need staging)

> **Deploy / verify / rollback path:** executable runbook
> [`docs/ops/deploy-verify-runbook.md`](../ops/deploy-verify-runbook.md) (migrations →
> OCI API → Vercel/DNS → n8n activation → rollback drills) and read-only post-deploy
> verifier [`scripts/ops/verify_live.sh`](../../scripts/ops/verify_live.sh) (G0–G9 matrix).

These five artifacts are **built and unit/mock-verified on master** but their
**live run requires the staging environment**, which this build env lacks.

- [ ] **E2E suite green on staging** vs Lenco sandbox (M16-P07 — 5 Playwright specs, Fast-3G/360px). — **Owner: Founder/Ops** _(staging + F9)_ — Evidence: _____
- [ ] **Restore drill ≤30min on staging** (M15-P09 — `restore-staging.sh`, 5 DR scenarios). — **Owner: Founder/Ops** _(staging)_ — Evidence: _____
- [ ] **Load test p95 <500ms @100cc on staging** (M16-P08 — k6 checkout+browse; post-run invariant check = zero oversell / ledger-imbalance / invoice-gap). — **Owner: Founder/Ops** _(staging)_ — Evidence: _____
- [ ] **Observability live-capture + alert fire** (M16-P06). — **Owner: Founder** _(DSN/UptimeRobot)_ — Evidence: _____
- [ ] **Deploy + rollback demonstrated on staging** (M01 criterion). — **Owner: Founder/Ops** _(staging)_ — Evidence: _____
- [ ] **Staging money drill** after place-order wiring (MoMo sandbox + COD + card session). — **Owner: Founder/Ops** _(staging + F9)_ — Evidence: runbook `docs/ops/staging-money-drill.md`
- [ ] **Apply migration 0066** (`user_wishlist` / `user_recently_viewed`) on staging before engagement sync QA. — **Owner: Founder/Ops** _(staging)_ — Evidence: _____

---

## 4. Founder gates F1–F9 (BLOCKING — all UNCHECKED)

Founder actions from `docs/plan/00-decisions.md`. **Each is a hard NO-GO for
real-money public launch until cleared.** They are founder-side, not code — do
**not** check them here on the founder's behalf.

- [x] **F1 — Domain:** ✅ **vergeo5.com purchased** (Porkbun, 2026-07-12). — **Owner: Founder** — Evidence: founder-confirmed in Porkbun account. _(Follow-up: vergeo5.co.zm still to acquire.)_
- [ ] **F2 — PACRA + TPIN:** annual-returns renewal + company TPIN (personal TPIN won't do for Lenco settlement / ZRA). — **Owner: Founder** — Evidence: _____
- [ ] **F3 — Lenco docs:** API docs + credential _names_ committed to `docs/ops/lenco/` (never secrets). — **Owner: Founder** — Evidence: `docs/ops/lenco/lenco-api-distilled.md` _(confirm complete)_
- [ ] **F4 — Counsel (escrow / NPS Act 2026):** Zambian counsel review of the Lenco-held escrow flow — **pre-real-money launch gate.** — **Owner: Founder + Counsel** — Evidence: _____
- [ ] **F5 — Meta/WhatsApp Cloud API:** Meta Business + WhatsApp Cloud API activation (real number needs F1). — **Owner: Founder** — Evidence: `docs/ops/whatsapp-cloud-api-setup.md`
- [ ] **F6 — Courier MOUs:** Platinum couriers / bus-freight conversations (post-beta acceptable). — **Owner: Founder** — Evidence: _____
- [ ] **F7 — Design files:** upload remaining **6** design HTML files (`docs/designs/SOURCES.md`). — **Owner: Founder** — Evidence: _____
- [ ] **F8 — COD cap:** confirm or invert D12's COD cap (≤K500 recommended). — **Owner: Founder** — Evidence: `platform_config.cod_cap_ngwee`
- [ ] **F9 — Lenco credentials (payments go-live):**
  - [ ] **F9a — Zamtel collections:** enable when Lenco confirms (currently payout-only; rail hidden at checkout). — **Owner: Founder** — Evidence: _____
  - [ ] **F9b — Lenco sandbox/production creds:** the live-payment gate — collection/payout + webhook integration + M16-P07 sandbox E2E leg. — **Owner: Founder** — Evidence: _____

---

## 5. Legal & compliance (pre-public)

- [ ] Terms, Privacy (Zambia DPA), Returns, Vendor Agreement published + linked from every footer + checkout consent. — Evidence: `apps/customer/app/[locale]/(marketing)/legal/{terms,privacy,returns,vendor-agreement}/page.tsx`; footer links in `apps/customer/app/[locale]/layout.tsx`; checkout consent `…/(shop)/checkout/_components/step-review.tsx` _(publish = go-live action)_
- [x] ZRA-ready sequential invoicing gapless under concurrency (tested); VAT flag off at launch; VSDC seam present. — Evidence: `services/api/tests/test_commissions_invoicing.py::TestInvoicingGapless::test_concurrent_invoice_issuance_gapless_sequence` (gapless under concurrency); `test_invoices.py` (`test_vat_block_absent_when_flag_off`, `test_vsdc_seam_is_stub_only`) — green in `Python API`
- [x] Prohibited-category listing blocked server-side (D8 fence). — Evidence: `services/api/tests/test_prohibited.py` (11 cases) — green in `Python API`
- [ ] Admin app on separate origin + allowlist; service-role key server-side only; secrets only in env. — Evidence: `Secret scan (gitleaks)` (no secrets in repo) · `services/api/tests/test_service_role_import_guard.py` (service-role server-side only); separate-origin + allowlist = Caddy/admin deploy config _(deploy)_

---

## 6. Beta operations (this pebble — M16-P09)

Build-verifiable in-repo. Link the merged M16-P09 PR + test run as evidence.

- [x] `beta_invites` migration `0030` applied; RLS+FORCE; admin read, no client write; redemption only via `redeem_beta_invite` (SECURITY DEFINER). — Evidence: `supabase/migrations/0030_beta_invites.sql` (`redeem_beta_invite`, RLS+FORCE) — applied to live (schema_migrations `0030`); covered by `services/api/tests/test_beta.py`, green in `Python API`
- [x] Redemption is atomic + **capacity-safe** (concurrent redeem never exceeds capacity — tested). — Evidence: `services/api/tests/test_beta.py::test_capacity_race_never_exceeds` — green in `Python API`
- [x] Gate is flag-controlled: `public_launch` OFF ⇒ invite required; ON ⇒ gate is a no-op (public), no deploy. — Evidence: `services/api/tests/test_beta.py` (`test_gate_invite_required_when_flag_off`, `test_gate_public_when_flag_on`, `test_gate_defaults_invite_only_when_flag_missing`, `test_redeem_is_noop_when_public_launch_on`) — green in `Python API`
- [x] Invite management admin-scoped + audited; feedback widget round-trips to the outbox (sanitized). — Evidence: `services/api/tests/test_beta.py` — green in `Python API`
- [ ] Invite cohort created + distributed for beta. — **Owner: Founder** — Evidence: _(admin `/beta/invites`)_

---

_Evidence reconciliation pass (2026-07-17, incremental on top of #233). Since #233
(master `1d728d5`) the tree shipped the **Events Phase-2 Wave B** epic end-to-end —
organiser pricing-write API (#232), organiser pricing UI (#235), customer
price-mode display (#236) + group-tier upsell (#248), and attendee-name capture +
organiser roster/CSV (#240/#243/#245) — plus **M15-P03** vendor commercial tier
(#247), the **OWASP F2** fix rejecting unsigned Lenco webhooks with 401 (#238), and
a **dormant** role-sync access-token hook (migration `0051`, #241 — present but NOT
enabled; enabling it is a founder/staging step). None of these change a launch gate:
Wave B is additive to M10, and the security fixes strengthen existing evidence.
Code-side evidence slots in Sections 1, 2, 5 and 6 stay filled by the proving
in-repo tests/CI jobs/scripts; **CI-job references are pinned to `d91479b` (#247)**,
the last commit merged through full required CI. The current tip `f2dadd5` (#248)
was **admin-merged bypassing CI** (this session's pushes were Actions-throttled);
its gates were verified locally instead — customer `typecheck` + `eslint` + the
blocking i18n sweep + 173 customer tests, all green. Only lines **wholly** satisfied
by currently-green **required** CI — with no staging, founder or advisory residual —
stay checked (Section 2: full API/typecheck/lint suite, blocking i18n sweep;
Section 5: invoice gapless-under-concurrency, prohibited-category fence; Section 6:
the four build-verifiable beta-ops lines). Mountain-level composites (Section 1),
Lighthouse (advisory), founder gates (F1–F9) and the five staging proofs (Section 3)
stay **unchecked by design** — see the Rule at the top. The repo migration ledger is
now `0001`–`0051`; `0051` (role-sync hook) ships **dormant** — applying it and
wiring the hook in Supabase Auth is a founder/staging step, so it changes no gate
here. **Sign Section 0 last.**_
