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

- [ ] **GO / NO-GO — Founder** has reviewed Sections 1–5; every BLOCKING gate is green. — **Owner: Founder** — Evidence: _(link decision record)_
- [ ] **Escrow real-money launch approved** — counsel gate **F4** cleared (Section 4). — **Owner: Founder + Counsel** — Evidence: _____
- [ ] **Payments live** — Lenco production credentials in place, sandbox E2E green (**F9**). — **Owner: Founder** — Evidence: _____
- [ ] **`public_launch` flip authorised** — flag flipped ON only after the three lines above are signed. — **Owner: Founder** — Evidence: _(admin audit_log entry)_
- [ ] **Rollback plan acknowledged** — flip `public_launch` OFF + DR runbook (M15-P09) on hand. — **Owner: Founder** — Evidence: `docs/ops/` DR runbook

---

## 1. Mountain success criteria (M01–M16)

Each mountain's Phase-1 success criteria (see `docs/plan/01-mountains.md`). Link
the merged pebble PRs / test runs as evidence. Items whose proof requires the
staging environment or a founder gate are tagged and stay **unchecked**.

- [ ] **M01 — Foundations/Infra:** fresh clone → `pnpm i && pnpm dev` runs all apps; CI green; deploy+rollback demonstrated _(staging)_; no secrets in repo (scanner). — Evidence: _____
- [ ] **M02 — Design system:** all screens build from the kit; preview renders every component with i18n keys; a11y ≥95; tokens single-source. — Evidence: _____
- [ ] **M03 — Data core:** `supabase db reset` clean; **RLS suite proves customer/vendor/admin isolation** (incl. cross-vendor denial); seed browsable; types compile; hot queries use indexes. — Evidence: `services/api/tests/rls/` · _____
- [ ] **M04 — Auth:** phone-only signup→browse→order; client role-escalation impossible (tested); OTP brute-force blocked (tested); deletion cascades. — Evidence: _____
- [ ] **M05 — Catalog/Search:** exact/fuzzy/semantic search relevant on seed; comparison sorts by price/distance; PLP LCP ≤2.5s Fast-3G; rich results validate. — Evidence: _____
- [ ] **M06 — Ask Vergeo:** 20-Q eval grounded, zero fabricated listings; quota + kill-switch enforced; p95 <6s; cost/answer ≤$0.002. — Evidence: `services/api/tests/evals/` · _____
- [ ] **M07 — Cart/Checkout:** two concurrent buyers cannot oversell last unit (race test); guest→auth merge preserves cart; ≤4 steps at 360px; reservation expiry restocks; COD ≤K500 enforced. — Evidence: _____
- [ ] **M08 — Payments/Escrow:** sandbox E2E charge→webhook→hold→confirm→release→payout for all 3 rails + card _(founder: F9)_; ledger balances (Σ postings = 0); dup/out-of-order/forged webhooks handled; reconciliation matches to the ngwee; every payment endpoint authz + rate-limited. — Evidence: _____
- [ ] **M09 — Orders/Fulfilment:** every legal transition tested + illegal rejected; QR verify offline-tolerant + single-use; auto-confirm/release idempotent; refund math exact. — Evidence: _____
- [ ] **M10 — Events/Ticketing:** create→publish→sell→QR-validates-once (offline incl.)→escrow settles per rule; screenshot QR fails after 60s; oversell impossible at capacity (race test). — Evidence: _____
- [ ] **M11 — Services/RFQ:** job→quotes→accept→deposit→complete→balance→review E2E; providers can't see each other's quotes; pre-acceptance contact-strip (tested). — Evidence: _____
- [ ] **M12 — Vendor portal:** unassisted T1 signup→KYC→first listing ≤10min; CSV 100-row mixed-error row feedback; caps enforced server-side; daily-driver one-handed 360px. — Evidence: _____
- [ ] **M13 — Admin/Merch:** every mutation audited (who/what/before/after); merch change reflects on home ≤1min no-deploy; KYC queue end-to-end; reconciliation flags injected mismatch. — Evidence: `services/api/tests/test_admin_audit.py` · _____
- [ ] **M14 — Notifications:** lifecycle fires exactly once per event (dedupe tested); WhatsApp→SMS fallback ≤2min _(founder: F5)_; STOP honored cross-channel; founder digest daily. — Evidence: _____
- [ ] **M15 — Trust/Security/Compliance/Legal:** OWASP zero criticals; **restore drill ≤30min** _(staging — M15-P09)_; legal pages linked from footers + checkout consent; invoice numbers gapless under concurrency (tested); prohibited-category listing blocked server-side. — Evidence: _____
- [ ] **M16 — Perf/PWA/Analytics/Launch QA:** all budgets green in CI on launch commit; **E2E green on staging vs Lenco sandbox** _(staging — M16-P07)_; **load p95 <500ms @100cc** _(staging — M16-P08)_; **beta cohort invitable/gated** (this pebble); go/no-go signed (Section 0). — Evidence: _____

---

## 2. Performance & quality budgets (CI-enforced)

- [ ] Customer routes ≤150KB gz JS on the launch commit. — Evidence: `bundle-guard` run _____
- [ ] LCP ≤2.5s Fast-3G / 360px; Lighthouse mobile Perf ≥90 / SEO ≥95 / A11y ≥95. — Evidence: `lighthouserc.json` run _____
- [ ] i18n completeness lint green (no hardcoded strings, no missing keys, no formatK bypass). — Evidence: `scripts/ci/i18n-lint.mjs` run _____
- [ ] Full API suite + typecheck + lint green (`uv run pytest`, `ruff`, `mypy`; turbo `test/lint/typecheck`). — Evidence: CI run _____
- [ ] Observability live: Sentry capturing, error budget 99.5% dashboard _(founder: DSN/UptimeRobot — M16-P06)_. — Evidence: _____

---

## 3. Staging-gated live-execution proofs (all UNCHECKED — need staging)

These five artifacts are **built and unit/mock-verified on master** but their
**live run requires the staging environment**, which this build env lacks.

- [ ] **E2E suite green on staging** vs Lenco sandbox (M16-P07 — 5 Playwright specs, Fast-3G/360px). — **Owner: Founder/Ops** _(staging + F9)_ — Evidence: _____
- [ ] **Restore drill ≤30min on staging** (M15-P09 — `restore-staging.sh`, 5 DR scenarios). — **Owner: Founder/Ops** _(staging)_ — Evidence: _____
- [ ] **Load test p95 <500ms @100cc on staging** (M16-P08 — k6 checkout+browse; post-run invariant check = zero oversell / ledger-imbalance / invoice-gap). — **Owner: Founder/Ops** _(staging)_ — Evidence: _____
- [ ] **Observability live-capture + alert fire** (M16-P06). — **Owner: Founder** _(DSN/UptimeRobot)_ — Evidence: _____
- [ ] **Deploy + rollback demonstrated on staging** (M01 criterion). — **Owner: Founder/Ops** _(staging)_ — Evidence: _____

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
- [ ] **F7 — Design files:** upload remaining 7 design HTML files (`docs/designs/SOURCES.md`). — **Owner: Founder** — Evidence: _____
- [ ] **F8 — COD cap:** confirm or invert D12's COD cap (≤K500 recommended). — **Owner: Founder** — Evidence: `platform_config.cod_cap_ngwee`
- [ ] **F9 — Lenco credentials (payments go-live):**
  - [ ] **F9a — Zamtel collections:** enable when Lenco confirms (currently payout-only; rail hidden at checkout). — **Owner: Founder** — Evidence: _____
  - [ ] **F9b — Lenco sandbox/production creds:** the live-payment gate — collection/payout + webhook integration + M16-P07 sandbox E2E leg. — **Owner: Founder** — Evidence: _____

---

## 5. Legal & compliance (pre-public)

- [ ] Terms, Privacy (Zambia DPA), Returns, Vendor Agreement published + linked from every footer + checkout consent. — Evidence: `apps/customer/app/[locale]/(marketing)/legal/` _____
- [ ] ZRA-ready sequential invoicing gapless under concurrency (tested); VAT flag off at launch; VSDC seam present. — Evidence: `services/api/tests/test_invoices.py` _____
- [ ] Prohibited-category listing blocked server-side (D8 fence). — Evidence: `services/api/tests/test_prohibited.py` _____
- [ ] Admin app on separate origin + allowlist; service-role key server-side only; secrets only in env. — Evidence: _____

---

## 6. Beta operations (this pebble — M16-P09)

Build-verifiable in-repo. Link the merged M16-P09 PR + test run as evidence.

- [ ] `beta_invites` migration `0030` applied; RLS+FORCE; admin read, no client write; redemption only via `redeem_beta_invite` (SECURITY DEFINER). — Evidence: `supabase/migrations/0030_beta_invites.sql`
- [ ] Redemption is atomic + **capacity-safe** (concurrent redeem never exceeds capacity — tested). — Evidence: `services/api/tests/test_beta.py::test_capacity_race_never_exceeds`
- [ ] Gate is flag-controlled: `public_launch` OFF ⇒ invite required; ON ⇒ gate is a no-op (public), no deploy. — Evidence: `services/api/tests/test_beta.py` (gate/flag tests)
- [ ] Invite management admin-scoped + audited; feedback widget round-trips to the outbox (sanitized). — Evidence: `services/api/tests/test_beta.py`
- [ ] Invite cohort created + distributed for beta. — **Owner: Founder** — Evidence: _(admin `/beta/invites`)_

---

_Last updated by pebble M16-P09. Founder-gated and staging-gated lines are
intentionally unchecked — see the Rule at the top. **Sign Section 0 last.**_
