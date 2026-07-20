# Vergeo5 — Vision-vs-Master Gap Report

**Question:** How far is the code in `master` from being a faithful representation of the project expectations documented in `docs/{concept,designs,ops,plan,production-readiness}`?
**Date:** 2026-07-20 · **Master tip audited:** `1d137ae` (PR #351) · **Baseline:** the repo's own `2026-07-19` vision-audit, re-scored against current master.

> **Read-scope honesty.** I can verify the **BUILD** lens directly (code inspection of this checkout). I **cannot** verify the **DEPLOY** (running in prod) or **VERIFY** (proven with real money/data) lenses from here — production is egress-blocked in this environment, and the last live probes in the repo are dated 2026-07-19. DEPLOY/VERIFY figures below are grounded in that last-known live state plus repo evidence, and are flagged where stale. Treat BUILD % as measured; DEPLOY/VERIFY % as best-estimate.

---

## 1. Headline

| Lens | What it means | Estimate | Confidence |
| ---- | ------------- | :------: | ---------- |
| **BUILD** | The code for the documented vision exists in `master` | **~94%** | High (measured) |
| **DEPLOY** | That code is running on production domains | **~55%** | Low (live not re-probed here; 2026-07-19 state) |
| **VERIFY** | Money/trust/exactly-once paths proven end-to-end with real data | **~25%** | Low (no drills evidenced) |
| **OPS** | Backup, observability, alerting in place | **~40%** | Medium |
| **LEGAL / DECISIONS** | Counsel posture + founder gates resolved | **~60%** | Medium |
| **Launch-ready (product of the above)** | Safe to take real money at open launch | **~45–50%** | — |

**One-sentence answer:** the **product is essentially built** (~94% of the documented feature vision exists as code), but it is **not yet a launch-ready representation** of the vision — the remaining distance is almost entirely **deploy + verify + ops + legal**, not missing features. The single biggest lie the current state could tell is "we handle real money," which is **built but unproven**.

---

## 2. What changed since the 2026-07-19 audit (master moved forward)

The 07-19 audit listed a set of **blockers**; several have since been **closed in code** by PRs #332–#351. Re-scored:

| 07-19 blocker | Status on master `1d137ae` | Evidence |
| ------------- | -------------------------- | -------- |
| Internal `/internal/*` token fail-**open** to `dev-*` default | ✅ **Fixed** — fail-closed | `app/core/internal_token.py` (#338) |
| Payout cross-worker double-pay | ✅ **Fixed** — `pg_advisory_xact_lock` reservation | `payouts/reservation.py` (#335) |
| Escrow release not fail-closed | ✅ **Fixed** | `escrow/release.py` (#333) |
| COD release not fail-closed | ✅ **Fixed** | (#342) |
| Refund/release double-drain race | ✅ **Fixed** — shared order-money gate | `escrow/order_money_gate.py` (#340) |
| Organiser Tier-1 GMV fraud cap (BG-3) | ✅ **Built** | `events/gmv_cap.py` + `0060_organiser_t1_gmv_cap.sql` (#343) |
| Multi-item refund over-refund; review-reply column tampering | ✅ **Fixed** | PR #344 (this session) — `0061_review_reply_column_guard.sql`, item-scoped refunds |
| Vendor/events/services lifecycle client-write guards | ✅ **Built** | `0057`/`0058` (#334/#337) |

**Net:** the backend money/trust **BUILD** gap has narrowed materially in the last day. The remaining blockers are now **rollout + verification + ops + legal**, which is why BUILD scores high but launch-ready does not.

---

## 3. Completeness by surface

| Surface | BUILD | DEPLOY* | VERIFY* | Notes |
| ------- | :---: | :-----: | :-----: | ----- |
| **Customer web** (`apps/customer`) | ~96% | ~70% | ~20% | All screens exist (home/PLP/PDP/compare/cart/checkout/events/services/directory/ask/account/privacy). Live gaps are demo imagery, honesty copy, fail-closed API base residuals. |
| **Vendor web** (`apps/vendor`) | ~95% | ~60% | ~10% | Onboarding+KYC, listings+CSV, events+**offline scanner**, orders, payouts, analytics all built. 0 real vendors exercised. |
| **Admin web** (`apps/admin`) | ~92% | ~60% | ~10% | Dashboard/KYC/moderation/disputes/merch/config/translations all present (moderation + config hub pages now exist). No generic user/role UI — **out by decision D33**. |
| **Backend API** (`services/api`) | ~97% | ~70% | ~25% | 88 routers, 62 migrations, RLS on every table, guarded state machines, double-entry ledger, money gates. Money paths built but **not proven with a real Lenco settlement**. |
| **Automations** (`infra/n8n`) | ~85% | ~30% | ~10% | 19 workflow JSON shells → real `/internal/*` routes exist; only ~2 live (dispatch, reconciliation). Release-job/tickets-issue/event-release **not activated**. **DB-backup workflow has no JSON at all.** |
| **i18n / vernacular** | ~55% | n/a | n/a | EN complete (17 namespaces); **Bemba/Nyanja are stubs** (8 files each, notifications only) — the D27 vernacular promise is unmet. |
| **Ops / observability** | ~40% | ~30% | ~10% | Sentry code wired but **no Vergeo5 Sentry projects/DSNs**; **no backup/restore drill**; uptime webhook unauthenticated. |
| **Compliance / legal** | ~50% | n/a | ~0% | Zambia-DPA privacy UX built; **NPS-Act escrow posture + written counsel NOT_AUDITABLE**; demo catalogue still public-eligible. |

\* DEPLOY/VERIFY reflect the 2026-07-19 live probe + repo state; not re-probed live this session.

---

## 4. Exactly what is MISSING — categorized

### 4A. Genuinely un-built / partial code (the real BUILD gap)
1. **Bemba & Nyanja translations (BG-1)** — *major.* Routable but stub; only `notifications.json` populated. ~15 namespaces × 2 locales unfilled. The D27 "EN → Bemba/Nyanja" promise is the largest true BUILD gap.
2. **DB-backup n8n workflow (BG-5 / X-2)** — *blocker.* Only a spec (`backup-schedule.md`); **no workflow JSON**. No nightly dump, no restore drill. This is a data-loss exposure, not just an ops nicety.
3. **Offline scanner cache completeness (BG-4)** — *major.* Scaffolding exists (`events/[id]/scan/_lib/offline-store.ts`, `scan-sync-client.ts`); "first-scan-wins" offline-then-sync needs finishing + proof.
4. **Uptime-alert webhook auth** — *major.* `/webhook/uptime-alert` planned unauthenticated; needs a shared-secret/HMAC before activation.
5. **Money-workflow error alerting** — *major.* Idempotency lives in the API; the n8n money ticks (release/recon/payout) have **no error-alerting/retry surface**.

**Deferred/out by locked decision — NOT counted as gaps:**
- Shoppable "Vergeo Clips" video feed (BG-6) — deferred post-launch by design.
- Product-model breadth: `product_class` A–E, used-goods, 5 pricing modes (BG-7) — **OUT (D34: Class-A new/refurbished only)**.
- Wishlist / recently-viewed / saved-search (BG-8) — **OUT of v1**.
- Admin generic user/role-management UI (BG-2) — **downgraded to a docs/manual-ops path (D33)**; single `admin` + Cloudflare Access is the v1 model.
- Event `multi_day` type (BG-9) — accept `standard`+`ends_at` (default).

### 4B. Deployment lag (code exists, not running) — **the dominant near-term gap**
> Every item here is closable by promote/apply/activate — **no feature work**. Status is per 2026-07-19; re-probe needed.
1. **Customer prod promotion** — prod was on `cc4a824` (pre-categories-fix); `/categories` returned HTTP 500. Fix merged, needs promotion. *(May already be resolved — verify.)*
2. **6 DB migrations unapplied live** — role hook `0051`, translation overrides, service reviews/bookable, **KYC integrity `0056`** — plus everything `0057`–`0062` merged since. Live DB lagged repo badly at 07-19.
3. **n8n money/ticket workflows dormant** — escrow auto-release and ticket issuance **cannot fire** until activated (17 of 19 shells inactive).
4. **API container digest not pinned/audited** — deployed image may lag master (esp. the new money gates).
5. **Seller CTA env** (`NEXT_PUBLIC_VENDOR_APP_URL`), **Sentry DSNs**, **staging plane** — all unset/unprovisioned.
6. **Fail-closed API base residuals** — 25 `?? "http://localhost:8000"` fallbacks remain in customer/vendor/admin clients; must fail-closed in prod.

### 4C. Verification gaps (built + maybe deployed, but unproven) — **the trust gap**
1. **Prepaid MoMo/card → escrow → release → payout** never exercised end-to-end with a real (even sandbox) Lenco settlement. `payments/orders/ledger = 0`.
2. **Refund/cancel/dispute matrix**, **exactly-once ticket issuance**, **escrow auto-release timers** — all logic present, none drilled.
3. **Search health** — `/search` observed `degraded=true` (embeddings/FTS) at 07-19; diagnose.
4. **Notification send** (WA→SMS→email) — outbox built, 0 real sends proven.
5. **RLS role-isolation** — matrix tests pass against ephemeral PG, but live role hook `0051` unapplied → JWT roles lag `user_roles`.

### 4D. Ops / cross-cutting
- **No Sentry projects**, **no backup artifact/restore drill**, **CI `secret-scan` is `continue-on-error`** (advisory, not blocking), **Lighthouse advisory** (perf budgets not enforced), **leaked-password protection disabled** in Supabase Auth.
- **Infra reality (from Drive evidence):** the OCI VM also hosts WAHA + a separate product (`zedcv-backend`) — noisy-neighbor + WhatsApp-ban blast-radius risk against the shared brand/number. Not in the capacity/isolation plan.

### 4E. Founder decisions / legal still open
- **Legal (X-4)** — NPS-Act escrow lawfulness + Zambia-DPA posture need **written counsel**; currently NOT_AUDITABLE. This is a hard real-money blocker.
- Most other FDs are **LOCKED** (D30 hybrid live-beta, D31 role hook, D32 FORCE-RLS, D33 single-admin, D34 Class-A) — those are resolved, not gaps.

---

## 5. The distance to 100%, by milestone

| To reach… | You must close… | Rough effort |
| --------- | --------------- | ------------ |
| **"Honest no-money live beta"** (~1–2 weeks) | 4B promotions + apply migrations + fail-closed API base + honesty copy + demo-catalogue exclusion | Mostly ops, small code |
| **"Real-money launch-ready"** (~3–6 weeks) | 4C money/ticket/refund **verification drills** + activate n8n money workflows + **legal counsel** + **backup/restore drill** + Sentry | Ops + verification + legal, little build |
| **"Full vision representation"** (post-launch) | 4A Bemba/Nyanja fill + offline-scanner finish + money-workflow alerting + (optionally) the OUT-by-decision items if re-scoped | Real but non-blocking build |

---

## 6. Bottom line

- **As a *feature* representation of the docs: ~94% there.** Almost everything the concept/designs/plan describe exists as code, and the last day closed most remaining backend money/trust blockers.
- **As a *launch-ready, trustworthy* representation: ~45–50% there.** The gap is **deploy it, prove the money, wire the ops, get the legal sign-off** — verification and rollout, not construction.
- **The one thing to internalize:** the codebase is ahead of its evidence. Nothing here is safe to call "done" for real money until a sandbox Lenco settlement, a refund, a ticket issuance, an escrow auto-release, and a backup-restore have each been *run and observed* — because today all five are code-complete but zero-proven.
