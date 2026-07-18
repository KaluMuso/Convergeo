# Panel PR integration review — 2026-07-18

**Reviewer role:** Convergeo release integration reviewer  
**Reviewed against:** `origin/master` @ `2fc6b79fe57a7e1162b1c0367fbd5f2b24e1136f`  
**Subject PRs:** [#289](https://github.com/KaluMuso/Convergeo/pull/289) (customer), [#290](https://github.com/KaluMuso/Convergeo/pull/290) (admin), [#291](https://github.com/KaluMuso/Convergeo/pull/291) (vendor)  
**Constraints honoured:** no production deploy, no merge actions, no DB data changes, no environment-variable changes, no unrelated code edits

---

## Executive verdict

| PR       | Title                                                   | GitHub state                                | Integration verdict |
| -------- | ------------------------------------------------------- | ------------------------------------------- | ------------------- |
| **#289** | CUST-03/04/07/08/10 customer panel hardening            | **MERGED** `5596853` (2026-07-18T20:37:20Z) | **PASS**            |
| **#290** | ADM-06/07 admin analytics honesty + D16 dispatch UX     | **MERGED** `3c1983f` (2026-07-18T20:38:48Z) | **PASS**            |
| **#291** | VEND-01/03/08 vendor onboarding, catalogue, KYC honesty | **MERGED** `2fc6b79` (2026-07-18T20:39:17Z) | **PASS**            |

All three panel readiness PRs are already on `master`. File ownership was exclusive (zero path overlaps), merges were clean, and the combined tree passes workspace lint / typecheck / unit tests / production builds for customer, vendor, and admin.

**Conflict resolution required:** none.

**Deployment:** still blocked by non-panel release risks (see below). Do not treat these merges as a go-live.

---

## 1. Merge status vs current master

All three PRs shared the same original base:

| Field           | Value                                      |
| --------------- | ------------------------------------------ |
| Common base OID | `9b71fb91161fbfaecf15916399098f63eb08811d` |
| #289 head       | `0c25baeaae19b0dc2ff5b5cffc5ad8cd8a5b2887` |
| #290 head       | `4783b254a4872010f81358e9b72f665c22a025d8` |
| #291 head       | `56929208f7469c616e7c0f809385fff1e4907fff` |

Ancestry check (each head is an ancestor of current `origin/master`): **PASS** for all three.

Actual merge order on master:

1. `#289` → `5596853`
2. `#290` → `3c1983f`
3. `#291` → `2fc6b79` (current tip)

No conflict markers remain under `apps/{customer,vendor,admin}`, `packages/i18n/messages`, or `docs/production-readiness/2026-07-18/implementation`.

---

## 2. Overlap / collision analysis

### 2.1 Overlapping file edits

| Pair           | Shared paths |
| -------------- | ------------ |
| #289 ∩ #290    | **none**     |
| #289 ∩ #291    | **none**     |
| #290 ∩ #291    | **none**     |
| Triple overlap | **none**     |

File counts: customer 29 · admin 23 · vendor 26 (78 total, all unique).

### 2.2 Shared-package edits

| PR   | `packages/i18n` files                               |
| ---- | --------------------------------------------------- |
| #289 | `messages/{en,fr,zh}/catalog.json`, `checkout.json` |
| #290 | `messages/{en,fr,zh}/admin.json`                    |
| #291 | `messages/{en,fr,zh}/vendor.json`                   |

**No shared-package file collisions.** Message namespaces are partitioned by app (`catalog`/`checkout` vs `admin` vs `vendor`). No `@vergeo/ui|types|config|auth` package source edits in any of the three PRs.

### 2.3 Translation conflicts

None. Locale parity is consistent (en/fr/zh touched together per PR). No key collisions across JSON files.

### 2.4 Route collisions

| PR   | New / changed customer-visible routes                                                  |
| ---- | -------------------------------------------------------------------------------------- |
| #289 | `/[locale]/categories`, `/[locale]/compare`, `/[locale]/calendar` (permanent redirect) |
| #290 | none (admin-only surfaces)                                                             |
| #291 | none new (existing vendor routes: listings/onboarding/profile/analytics/home)          |

**No cross-app route collisions.** Customer calendar → events redirect does not collide with vendor/admin trees.

### 2.5 Report-file collisions

| PR   | Report path                                                                     |
| ---- | ------------------------------------------------------------------------------- |
| #289 | `docs/production-readiness/2026-07-18/implementation/customer-change-report.md` |
| #290 | `docs/production-readiness/2026-07-18/implementation/admin-change-report.md`    |
| #291 | `docs/production-readiness/2026-07-18/implementation/vendor-change-report.md`   |

**No report-file collisions.**

---

## 3. Compile / validate against current master

Because all three heads are already ancestors of `master`, validating the combined tree at `2fc6b79` is the correct “compiles against current master” check (not replaying each branch tip in isolation).

| Check                 | Command                                            | Result                                                                                                                                                                  |
| --------------------- | -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lockfile-safe install | `pnpm install --frozen-lockfile`                   | **PASS (deps)** — lockfile up to date / already installed. `prepare` lefthook hook failed in this VM (`commit-msg.old` rename); non-blocking for dependency resolution. |
| Lint                  | `pnpm lint`                                        | **PASS** (turbo 5 tasks)                                                                                                                                                |
| Typecheck             | `pnpm typecheck`                                   | **PASS** (turbo 9 tasks)                                                                                                                                                |
| Unit tests            | `pnpm test`                                        | **PASS** (turbo 14 tasks) — see counts below                                                                                                                            |
| Customer prod build   | `NODE_ENV=production pnpm --filter customer build` | **PASS** — routes include `/[locale]/categories`, `/compare`, `/calendar`; serwist emits `/sw.js`                                                                       |
| Vendor prod build     | `NODE_ENV=production pnpm --filter vendor build`   | **PASS**                                                                                                                                                                |
| Admin prod build      | `NODE_ENV=production pnpm --filter admin build`    | **PASS**                                                                                                                                                                |

### Unit-test counts (combined master)

| Package             | Files | Tests |
| ------------------- | ----- | ----- |
| customer            | 36    | 207   |
| vendor              | 12    | 82    |
| admin               | 7     | 36    |
| `@vergeo/ui`        | 42    | 153   |
| `@vergeo/i18n`      | 4     | 19    |
| `@vergeo/auth`      | 3     | 22    |
| `@vergeo/analytics` | 2     | 11    |
| `@vergeo/config`    | 3     | 9     |

### Optional MR-B01 presence check (not a panel gate)

```bash
cd services/api && uv run pytest -q tests/test_prepaid_settlement.py
```

**Result:** `1 passed, 6 errors` — errors are **environment setup** (`FileNotFoundError: psql`; local Supabase DB fixture unavailable). Module import of `settle_prepaid_collection` succeeds. This does **not** fail the panel PRs; it confirms PR #274 code is present but staging/live evidence is still required.

---

## 4. Panel claim truthfulness

### 4.1 PR #289 — customer

| Claim                                                            | Verdict                  | Evidence                                                                                                                                 |
| ---------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| No fake paid/success UI                                          | **TRUE (UI)**            | `resolveCardVerifyViewState` requires `order_confirmed`; MoMo `success` → `confirming`, never standalone paid                            |
| Production localhost fail-closed on checkout payment verify/poll | **TRUE (touched paths)** | `card/[paymentId]/page.tsx` + `ussd-wait.tsx` use `resolveApiBaseUrl()`                                                                  |
| No invented analytics/escrow amounts                             | **N/A / OK**             | No analytics/escrow inventing in this PR                                                                                                 |
| Categories / compare / calendar honesty                          | **TRUE**                 | Live category tree / comparison API / redirect; honest empties covered by tests                                                          |
| Full checkout localhost fail-closed                              | **PARTIAL residual**     | `checkout/_components/step-{payment,contact,fulfillment}.tsx` still use `?? "http://localhost:8000"` — outside the PR’s hardened helpers |

### 4.2 PR #290 — admin

| Claim                                             | Verdict                    | Evidence                                                                         |
| ------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------- |
| No invented analytics (“Balanced” without report) | **TRUE**                   | `reconciliationDisplayStatus` → `unknown` when `report_id`/`report_date` missing |
| No invented escrow amounts                        | **TRUE**                   | Escrow amount input defaults to `""`; ledger summary is count/kinds only         |
| No privilege/RBAC UI without API                  | **TRUE**                   | No role grant/revoke/invite UI added; ADM-01/02 explicitly deferred              |
| Localhost fail-closed                             | **NOT CLAIMED / residual** | `apps/admin/app/[locale]/_components/api.ts` still falls back to localhost       |

### 4.3 PR #291 — vendor

| Claim                                          | Verdict                    | Evidence                                                                        |
| ---------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------- |
| No KYC tier as verification without KYC record | **TRUE (UI)**              | `isAuditableApproved` requires `kyc_record_id` + approved status                |
| No invented analytics / GMV                    | **TRUE**                   | Analytics empty state when sales/orders/views all zero                          |
| No staff/RBAC UI                               | **TRUE**                   | No staff/invite/role surfaces; quick-nav is owner capability links only         |
| Localhost fail-closed                          | **NOT CLAIMED / residual** | Touched files `order-card.tsx` and `kyc-client.ts` still use localhost fallback |

### 4.4 Cross-app residual (not a false PR claim)

Customer storefront vendor profile still badges from bare `kyc_tier` (`apps/customer/.../v/[slug]/page.tsx`). That path was outside #289/#291 scope; vendor UI honesty does not yet extend to customer-facing badges.

---

## 5. PR #274 (MR-B01) presence + wording updates

### 5.1 Presence on master

| Check                      | Result                                                                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| PR #274 state              | **MERGED** 2026-07-18T14:53:15Z                                                                                                       |
| Merge commit               | `17b2658fab2cb953c84893f19f39704f9df0fb84`                                                                                            |
| Ancestor of current master | **yes**                                                                                                                               |
| Code present               | `services/api/app/services/payments/settlement.py` (`settle_prepaid_collection` → `CHARGE_RECEIVED`); hooked from `payments/state.py` |
| Staging/live evidence      | **still required** (sandbox MoMo/card → ledger SQL not verified in this review)                                                       |

### 5.2 PR-report wording that should be updated

None of the three panel reports literally say “MR-B01 missing,” but several lines still read as if the API hook is unimplemented. Update those to: **“MR-B01 merged (#274) but still requires staging/live evidence.”**

| File                                                           | Current wording (approx.)                                                   | Recommended update                                                                                                        |
| -------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `implementation/customer-change-report.md` §CUST-08 acceptance | “full ledger confirmation still needs API MR-B01”                           | “MR-B01 merged (#274); full ledger confirmation still requires staging/live evidence + payment-status contract surfacing” |
| `implementation/customer-change-report.md` deferred table      | “Ledger post confirmation not on payment-status contract (MR-B01 / MR-W01)” | Keep MR-W01; restate MR-B01 as **merged but unproven live**                                                               |
| `implementation/customer-change-report.md` release risk #1     | “G4 still FAIL until MR-B01”                                                | “G4 still FAIL until MR-B01 staging/live evidence (code landed in #274)”                                                  |
| `implementation/vendor-change-report.md` VEND-08 / deps table  | “Ledger-backed organiser fees still MR-B01” / “MR-B01 — prepaid → ledger”   | “MR-B01 merged (#274); organiser money stats still blocked on staging/live ledger evidence (+ product wiring)”            |
| `implementation/admin-change-report.md` ADM-08 notes           | “MR-B01/MR-W01 dependency labelled”                                         | “MR-B01 merged (#274) but still requires staging/live evidence; MR-W01 still open”                                        |

Related consolidated docs (outside these PR reports, but stale vs #274):

- `consolidated/master-reconciliation-register.md` still describes prepaid path as “no `post_transaction(CHARGE_RECEIVED/ESCROW_HOLD)` … likely missing”
- `consolidated/24-hour-workboard.md` I-01 still says “implement missing `post_transaction`”

Those should be refreshed in a follow-up docs pass to the same “merged but staging/live evidence required” language.

---

## 6. Recommended merge sequence

**Already executed on master:** `#289` → `#290` → `#291`.

If these had still been open drafts, the recommended sequence would be the same:

1. **Customer (#289)** first — payment false-success / localhost fail-closed for money paths
2. **Admin (#290)** second — ops honesty dependent on ledger visibility narrative
3. **Vendor (#291)** last — KYC/catalogue honesty with no shared-file risk

Any order would have been mechanically safe (zero overlaps). The above order is preferred for release storytelling and residual-risk priority.

**Exact conflict resolution:** none required.

---

## 7. Release risks that still block deployment

These panel PRs improve honesty; they do **not** clear go-live. Remaining blockers:

| ID / theme                              | Severity | Why still blocking                                                                                                                                                  |
| --------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MR-B01 staging/live evidence**        | P0       | Code merged via #274; no sandbox MoMo/card → balanced ledger proof in this review; G4 residual (MoMo redirects to order without ledger field on `/payments/status`) |
| **MR-W01 escrow release n8n**           | P0       | Auto-release workflow still missing/inactive for production money path                                                                                              |
| **CUST-01 / G10 vendor CTA env**        | P0/P1    | Needs live `NEXT_PUBLIC_VENDOR_APP_URL` on Vercel (not set in this review; code fail-closed)                                                                        |
| **CUST-02 / G11 demo catalogue**        | P1       | Demo inventory still public without disclosure/exclude                                                                                                              |
| **MR-D02 / ADM-03 / G12 KYC integrity** | P0       | Seed `kyc_tier` without `kyc_records` remains a data/API defect; vendor UI only                                                                                     |
| **ADM-01/02 admin RBAC**                | P0       | Founder decision + role contracts still open; UI correctly not fabricated                                                                                           |
| **Localhost residuals**                 | P1       | Non-hardened API base fallbacks remain in customer checkout steps, vendor, and admin clients                                                                        |
| **Customer storefront KYC badges**      | P1       | Still may show tier from bare `kyc_tier` on `/v/[slug]`                                                                                                             |
| **DB migrations / n8n / ops gates**     | P0–P1    | Foundation register items (migrations behind, tickets-issue, backups proof) unchanged by these PRs                                                                  |
| **Deploy evidence**                     | P1       | Live SW 200, Access-authenticated admin smoke, vendor JWT KYC attach audit still undeployed/unproven                                                                |

**Do not deploy** from the panel readiness work alone.

---

## 8. Commands run and results (exact)

```bash
git fetch origin master
# master @ 2fc6b79fe57a7e1162b1c0367fbd5f2b24e1136f

gh pr view 289|290|291|274 --json ...   # all three panel PRs MERGED; #274 MERGED

# Overlap: comm of file lists → empty intersections

git merge-base --is-ancestor <each-pr-head> origin/master   # all OK
git merge-base --is-ancestor 17b2658fab2cb953c84893f19f39704f9df0fb84 origin/master  # PR274 OK

pnpm install --frozen-lockfile
# deps: Already up to date / lockfile OK
# prepare lefthook: FAIL (VM hook rename); ignored for lockfile verification

pnpm lint            # PASS (exit 0)
pnpm typecheck       # PASS (exit 0)
pnpm test            # PASS (exit 0) — customer 207, vendor 82, admin 36, + packages

NODE_ENV=production pnpm --filter customer build   # PASS (exit 0)
NODE_ENV=production pnpm --filter vendor build     # PASS (exit 0)
NODE_ENV=production pnpm --filter admin build      # PASS (exit 0)

cd services/api && uv run pytest -q tests/test_prepaid_settlement.py
# 1 passed, 6 errors (missing psql / local DB) — env limitation, not panel regression
```

---

## 9. Per-PR pass/fail summary

| PR       | Integration PASS/FAIL | Notes                                                                                                                                                                           |
| -------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **#289** | **PASS**              | Merged cleanly; builds + 207 tests green; payment honesty + categories/compare/calendar landed; localhost residual in other checkout steps; update MR-B01 wording in its report |
| **#290** | **PASS**              | Merged cleanly; builds + 36 tests green; analytics/dispatch/escrow honesty holds; no fabricated RBAC                                                                            |
| **#291** | **PASS**              | Merged cleanly; builds + 82 tests green; KYC record gating + empty analytics hold; staff RBAC correctly OUT                                                                     |

**Overall integration:** **PASS** — no merge conflicts, no shared-package/route/report collisions, combined master validates.  
**Release go-live:** **FAIL / blocked** — staging/live money, KYC data, n8n, env, and residual honesty gaps remain.
