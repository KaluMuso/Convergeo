# Vergeo5 — Launch Runbook (deploy → verify → ops → go-live)

**Written:** 2026-07-22 · **Master tip at write:** `9ae09cd` · **Standing verdict:** **NO_GO for real money** (correct). **Mode:** GATED.

> **Why this exists.** The build is code-complete (M01–M16; sweep of `9ae09cd` finds one code stub + one i18n gap — see `codebase-review-2026-07-21.md`). The launch-blocking gap is **DEPLOY + VERIFY + OPS + FOUNDER/LEGAL**, not engineering. This runbook is the ordered path from "green CI" to "real money on". It supersedes nothing in `docs/plan/launch-checklist.md` — it sequences it. Truth sources: `2026-07-20/go-no-go-report.md`, `current-implementation-board.md`, `2026-07-21/api-recovery-and-ops.md`.

**Legend:** Owner **F**=Founder · **O**=Ops · **C**=Counsel · **E**=Eng. "Done" = the observable proof; record evidence under `docs/production-readiness/<date>/`.

---

## Phase 0 — Preconditions (confirm before starting)

| #   | Item                                                   | Owner | Done                                                                                                                               |
| --- | ------------------------------------------------------ | ----- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 0.1 | CI green on the launch commit                          | E/O   | All 13 blocking jobs green (today: **`Bundle, image lint & Lighthouse` is RED** — fix first, see Appendix A)                       |
| 0.2 | Branch protection "do not allow bypassing" on `master` | O     | Required checks enforced; no admin-override merges (several recent PRs merged past red — close this)                               |
| 0.3 | Live fingerprint recorded                              | O     | `GET api.vergeo5.com/fingerprint` → `env=production`, real `git_sha` (currently **`unknown`** — bake the SHA into the image build) |

## Phase 1 — Deploy / promote (no real money; safe under `public_launch=false`)

| #   | Item                                                             | Owner | Done                                                                                                                                                              |
| --- | ---------------------------------------------------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.1 | Promote customer/vendor/admin to `master` tip                    | O     | Vercel prod SHAs == master tip; recorded. (OG edge bundle already <1 MB, `2ac18e7`.)                                                                              |
| 1.2 | Pin API image + record digest                                    | O     | `docker pull ghcr.io/kalumuso/convergeo-api:<tag>`; `/fingerprint` shows the digest + git SHA; money/KYC routes confirmed at source_key-era code                  |
| 1.3 | Apply outstanding migrations on the live DB                      | O     | `schema_migrations` tip == repo tip; **`0064` FORCE RLS + `0065` source_key confirmed applied**; advisors clean                                                   |
| 1.4 | Enable the Supabase Auth custom-access-token hook (D31 / `0051`) | O     | JWT `roles` == `public.user_roles`; RLS isolation suite green live                                                                                                |
| 1.5 | Activate the **money** n8n workflows                             | O     | `payment reconciliation crons` + `shared error alert` published (6 non-money already active); idempotent after Phase 2 drills; error-alert needs F5 WhatsApp cred |
| 1.6 | Set `NEXT_PUBLIC_VENDOR_APP_URL` + confirm API `CORS_ORIGINS`    | O     | vendor/admin origins reachable; sell CTA resolves                                                                                                                 |

## Phase 2 — Money-path proof on an isolated target (D30: sandbox + throwaway DB branch, NOT a full staging plane)

**Gate:** none of this runs live until it passes here. All money tables must be `0` before, and every leg idempotent (replay = no double-post).

| #   | Item (drill)                                                                    | Owner | Done                                                                                                      |
| --- | ------------------------------------------------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------- |
| 2.1 | **F9b — Lenco sandbox + prod credentials** in API env                           | F     | keys present; webhooks reachable at `/webhooks/{lenco,whatsapp}` — **unblocks every drill below**         |
| 2.2 | **S1/S2/S3** charge→webhook→hold→confirm→release→payout — MoMo + card + release | O     | ledger Σ postings = 0; hold legs posted; idempotent replay; reconciliation matches to the ngwee           |
| 2.3 | **S6** false-success matrix                                                     | O     | pending / failed / cancelled / malformed / timeout provider states **never** post as paid                 |
| 2.4 | **S5** KYC lifecycle                                                            | O     | submit→approve; privileges freeze without a KYC record; `kyc_records` moves off 0 in the drill            |
| 2.5 | **S4** automation exactly-once                                                  | O     | release / ticket-issue / event-release proven idempotent (no double release/issue) under the active crons |

## Phase 3 — Ops / reliability proofs

| #   | Item                                  | Owner | Done                                                                                                                                |
| --- | ------------------------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 3.1 | **G6** observability live             | F/O   | Sentry projects + DSNs created (currently none); a test event ingested per surface; UptimeRobot monitor fires with recorded latency |
| 3.2 | **G7** backup + ≤30-min restore drill | O     | dated OCI dump artifact + a timed restore ≤30 min (code done `infra/n8n/backup.json`; drill NOT_RUN)                                |
| 3.3 | **G9** rollback drill                 | O     | timed Vercel + API rollback recorded (NOT_RUN)                                                                                      |
| 3.4 | Load test p95 <500ms @100cc           | O     | k6 checkout+browse; post-run invariant check = zero oversell / ledger-imbalance / invoice-gap (NOT_RUN)                             |
| 3.5 | Search honesty                        | O     | `/search?degraded=` flips **false** after embeddings cron active + healthy `OPENROUTER_API_KEY` (embedding model dims fixed `#480`) |

## Phase 4 — Founder / legal gates (P0, all currently open except F1)

| #   | Gate                                                                           | Owner | Done                                                                                             |
| --- | ------------------------------------------------------------------------------ | ----- | ------------------------------------------------------------------------------------------------ |
| 4.1 | **F4 / L-01** — Zambian counsel review of Lenco-held escrow under NPS Act 2026 | F/C   | **written counsel sign-off** — hard gate before any real money                                   |
| 4.2 | **F2** — PACRA annual returns + **company** TPIN                               | F     | registered/confirmed (personal TPIN won't do for Lenco settlement/ZRA)                           |
| 4.3 | **F5** — Meta Business + WhatsApp Cloud API + approved templates               | F     | one live template send proven (also unblocks the money error-alert + event-cancel notifications) |
| 4.4 | **F8** — confirm COD cap                                                       | F     | `platform_config.cod_cap_ngwee` (currently `50000` = K500) confirmed or inverted                 |
| 4.5 | Legal pages **published** + linked from every footer + checkout consent        | F     | Terms/Privacy(DPA)/Returns/Vendor-Agreement live (pages exist in code; publish = go-live action) |

## Phase 5 — Go-live (sign LAST)

| #   | Item                          | Owner | Done                                                                                                              |
| --- | ----------------------------- | ----- | ----------------------------------------------------------------------------------------------------------------- |
| 5.1 | Go/No-Go evidence pack filled | O     | every earned gate flipped to PASS with evidence links                                                             |
| 5.2 | Founder Go/No-Go sign-off     | F     | Sections 1–5 reviewed; every BLOCKING gate green (supersede the agent NO_GO only with a written founder decision) |
| 5.3 | Flip `public_launch=true`     | F     | **only after 4.1–4.3 + Phase 2 pass**; recorded in admin `audit_log`                                              |
| 5.4 | Rollback ready                | F     | flip `public_launch=false` + DR runbook on hand                                                                   |

---

## Critical path (shortest chain to real money)

**F9b creds (2.1)** → Phase 2 drills (2.2–2.5) → **F4 counsel (4.1)** + **F2 (4.2)** + **F5 (4.3)** in parallel → observability/backup/rollback/load (Phase 3) → evidence pack (5.1) → sign-off (5.2) → flip (5.3). Phase 1 (deploy) and Phase 4 (founder gates) can run **in parallel** with the sandbox drills (D30 — neither waits on a full staging plane).

## Appendix A — the one red CI gate (blocks 0.1) — DIAGNOSED

`Bundle, image lint & Lighthouse` is failing on master, but **not on a code-size regression.** A local build of the customer app on `9ae09cd` was run and **every static gate in the job passes**: `bundle-guard` = "57 routes within budget", `i18n-lint` (sweep + self-test + pseudo-smoke) clean, `image-lint` clean, all guard self-tests pass, `validate-lighthouserc` OK. The failure is therefore in the job's **heavy tail** — the **`Start production server` step or the Lighthouse (LHCI) assertion run** (both need the built prod server + Supabase/API up, and assert per-route LCP/Perf/SEO/A11y floors). The `lighthouserc.json` note itself warns these floors "sit ~0.05–0.10 below cold-start scores" — i.e. **flake-prone**.

**Recommended action (no code change indicated):** (1) **re-run the failing job** — if it goes green, it was a Lighthouse/cold-start flake; (2) if it fails persistently, pull the LHCI output from the job log to see the exact route + assertion (e.g. an LCP > 6500 ms or a Perf score under floor) and either fix that route's LCP or adjust that one floor with justification; (3) if `Start production server` is the failure (server never answered `/en/health`), it's an env/boot issue in CI, not app code. Do **not** treat this as a bundle-budget problem — the budget is green.
