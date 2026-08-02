> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P09 — Real vendor/location data + a launch-blocking demo fence `[CODE+OPS]`

## 1. Context
**Wave W3.** Founder rule, verbatim: **never promote demo listings merely to make the catalogue look populated.**

Production currently holds **150 products / 134 vendor listings**, seeded from LoremFlickr demo imagery (`demo/categories/<slug>`, tags `demo,seed`). The exclusion machinery already exists and works — `app/services/listings/demo.py`, `drop_demo_listing_hits`, `tests/test_demo_exclusion.py` (VC-P06/FD-04/G11). What does not exist is a rule that **fails the build** if a demo listing can reach a public surface, and a path for real vendors to replace them.

A demo catalogue that is merely *filtered* is one config mistake away from being a live catalogue of products nobody can actually sell.

**Type:** `[CODE+OPS]`.

## 2. Objective & scope
Real vendors and branches onboarded with real inventory; the demo fence promoted from "tested" to "launch-blocking".
**Non-goals:** deleting demo data (it is useful in staging); marketing.

## 3. Files (edit ONLY these)
- `services/api/tests/test_demo_exclusion.py` — extend
- `scripts/ci/` — a new guard script if the assertion belongs in CI
- `.github/workflows/ci.yml` — wire the guard **blocking**
- `docs/ops/vendor-onboarding.md` (new)
- `docs/production-readiness/<YYYY-MM-DD>/real-catalogue-evidence.md` (new)

## 4. Implementation spec
- **The fence:** a check that fails if any listing whose media/public id matches the demo prefix, or whose vendor is flagged demo, is reachable from *any* public surface — PLP, PDP, search, suggest, comparison, storefront, Ask retrieval, sitemap, feed. Model it on `test_demo_exclusion.py` but make the failure mode "CI red", not "one test red among advisory ones". Note the existing precedent: `RLS isolation matrix` is `continue-on-error: true`, which is exactly the weakness to avoid repeating here.
- **A production-mode assertion:** when `ENV=production` and `public_launch=true`, starting with demo rows present on a public surface is a **startup-refusing** condition or a loud, alerting health degradation — the founder's call, but it must not be silent.
- **Onboarding runbook:** how a real vendor is created, KYC-verified, given branches (R02-P07) and per-branch stock (R02-P08), with real photography via the existing Cloudinary pipeline (`docs/ops/media-pipeline.md`). Reuse `create_listing_for_vendor(...)` — the single listing-creation seam — so an onboarded listing runs the identical prohibited-content screen and status resolution.
- **Evidence:** record real vendor count, real listing count, and the demo count that remains **excluded**, with the query used.

## 5. Security / conventions
No customer PII in committed evidence. Real vendor consent before any storefront goes live. Do not delete demo rows from staging.

## 10. Tests (RUN before reporting)
- The fence fails when a demo listing is deliberately made public; passes otherwise. **Show both runs** — a guard nobody has watched fail is a guard nobody should trust (see the staging-schema guard in R02-P01 for why).
- `uv run pytest services/api/tests/test_demo_exclusion.py -q`
- Full CI green with the guard blocking.

## 11. Acceptance criteria / DoD
- [ ] Demo listings cannot reach any public surface; the guard is **blocking**, and its failure mode has been demonstrated.
- [ ] ≥1 real vendor with ≥1 real branch and real listings, created through the normal seam.
- [ ] Evidence records real vs demo counts with queries.
- [ ] Onboarding runbook committed.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P09 — Real vendors + demo fence
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the deliberate-failure run and the passing run · **EXCERPTS:** the guard · **QUESTIONS:** …
