# Release truth — 2026-07-27 (RC-P01)

**Observation window (UTC):** 2026-07-27T21:30Z–23:45Z
**Observer:** Claude Code session (read-only; no deploy, no config change, no flag flip, no workflow activation, no money action)
**Scope:** reconcile `docs/plan/00-status.md` with what can actually be *verified* after M17 (Clips) and M18 (WhatsApp private intake) merged.
**Supersedes:** nothing. Dated packs are snapshots; this one records what was observable on this date and says plainly where it could not observe.

> **Reading rule.** Every row below is either **VERIFIED** (a tool returned it in this window) or
> **UNKNOWN** (no evidence was reachable). There is no third category. A merged PR, a green CI job
> and an applied migration are three different facts, and this document never lets one stand in for
> another.

---

## 0. What was reachable, and what was not

| Source                             | Reachable | Method                                                    |
| ---------------------------------- | --------- | --------------------------------------------------------- |
| Git / `origin/master`              | yes       | `git fetch` + `git rev-parse`                             |
| GitHub Actions                     | yes       | GitHub MCP `actions_list` / `get_job_logs`                |
| Supabase project `dpadrlxukcjbewpqympu` | yes  | Supabase MCP `list_migrations` + read-only `execute_sql`  |
| Vercel (3 projects)                | yes       | Vercel MCP `list_deployments`                             |
| n8n instance                       | yes       | n8n MCP `search_workflows`                                |
| `api.vergeo5.com`, `www/vendor/admin.vergeo5.com` | **no** | HTTPS egress denied by the session proxy (403 to CONNECT) |
| Cloudinary account plan/usage      | **no**    | not queried; F-V4 is a fact about the account, not the code |
| Lenco sandbox / production         | **no**    | credentials absent; no money action attempted             |

The unreachable rows are why §4 exists: they become **operator verification steps**, never inferred results.

---

## 1. Repository truth (VERIFIED)

| Fact                    | Value                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------ |
| `origin/master` tip     | `f85e8bd1e2c05d4a3972502d9fde3565feb618b1` — "Merge pull request #530", 2026-07-27T10:18:07Z |
| M17 merge trail         | #528 (P01) · #529 (P02+P03) · #530 (P04–P08)                                         |
| M18 merge trail         | #526 (P01–P06) · #527 (P07+P08)                                                      |
| Migration files present | `0072`–`0079`, **each exactly once**                                                 |
| Duplicate prefixes      | **none** repo-wide (`ls supabase/migrations | sed 's/_.*//' | sort | uniq -d` → empty) |

### 1.1 Migration order (VERIFIED by reading each file's DDL)

| File                          | Creates / alters                                                     | Depends on          |
| ----------------------------- | -------------------------------------------------------------------- | ------------------- |
| `0072_waha_intake_flag.sql`   | config rows only: `waha_vendor_intake` (**false**), empty allowlist  | `0008_config`       |
| `0073_waha_intake_model.sql`  | 7 intake tables + FORCE RLS + triggers                               | `0002`, `0072`      |
| `0074_intake_media_bucket.sql`| storage policies for `vendor-intake-media`, guarded `DO` block        | `0073`              |
| `0075_intake_handoff.sql`     | `intake_sessions.listing_id/submitted_at/admin_notes`, `intake_deep_links` | `0073`         |
| `0076_video_clips.sql`        | 6 clip tables, `clip_products` guard, `clip_bump_counter`            | `0002`, catalog     |
| `0077_clip_feature_flags.sql` | config rows only: `clips` (**false**), `clips_comments` (**false**)  | `0008_config`       |
| `0078_clip_weekly_caps.sql`   | `clip_weekly_caps` config                                            | `0076`              |
| `0079_clip_cost_guard.sql`    | `clip_spend_monthly`, `clip_record_spend`, `reset_clip_kill_switch`  | `0076`, `0008`      |

No file references an object created by a later-numbered file. Applying `0072 → 0079` in order is
dependency-safe.

### 1.2 Dark-ship posture in code (VERIFIED)

| Claim                                              | Evidence                                                                 |
| -------------------------------------------------- | ------------------------------------------------------------------------ |
| `clips` ships **false**                            | `0077_clip_feature_flags.sql` inserts `false`                            |
| `clips_comments` ships **false**                   | same file                                                                |
| `waha_vendor_intake` ships **false**               | `0072_waha_intake_flag.sql` inserts `false`; allowlist `[]`              |
| A **missing** flag row reads as disabled            | `app/services/clips/flags.py::_flag_enabled` and `app/services/intake/config.py` both return `False` on missing row *and* on read failure |
| No WAHA installed by this repo                      | `infra/docker-compose.yml` defines no WAHA service; `waha` appears only in `infra/.env.example` (names only) and the two n8n JSONs |

---

## 2. Deployment truth (VERIFIED / UNKNOWN)

### 2.1 Database — the headline

| Fact                             | Status       | Evidence                                                            |
| -------------------------------- | ------------ | ------------------------------------------------------------------- |
| Live migration ledger tip        | **VERIFIED** | `0071_vendor_listing_compare_at` (Supabase MCP `list_migrations`)   |
| `0072`–`0079` applied?           | **VERIFIED NO** | absent from the ledger                                            |
| M17/M18 tables exist live?       | **VERIFIED NO** | `to_regclass` null for `video_clips`, `clip_comments`, `clip_spend_monthly`, `clip_weekly_caps`, `intake_sessions`, `intake_deep_links` |
| `clips` / `clips_comments` / `waha_vendor_intake` rows exist live? | **VERIFIED NO** | not returned by a `feature_flags` select on those five keys |
| `public_launch`                  | **VERIFIED** | `false`                                                             |
| `zamtel_collections`             | **VERIFIED** | `false`                                                             |
| `payments` / `orders` / `ledger_transactions` / `kyc_records` | **VERIFIED** | `0` / `0` / `0` / `0`                          |
| `vendor_listings`                | **VERIFIED** | `134`                                                               |

**Why this matters, stated precisely.** Clips and intake are dark on live in the strongest available
sense: not merely flagged off, but **schema-absent**. The flag rows the runbooks refer to do not yet
exist on this project. Both readers fail closed on a missing row, so the posture is safe — but a
checklist line that says "confirm the row is `false`" cannot be ticked today; it becomes "confirm the
row exists and is `false`" *after* `0072`/`0077` are applied.

### 2.2 Frontends

| Project             | Production deployment | State     | Commit    |
| ------------------- | --------------------- | --------- | --------- |
| `convergeo-customer`| `dpl_BR9RCVHGth…`     | **READY** | `f85e8bd` |
| `convergeo-vendor`  | `dpl_EAqipUon8L…`     | **READY** | `f85e8bd` |
| `convergeo-admin`   | `dpl_7DTjAQdCLi…`     | **READY** | `f85e8bd` |

All three created 2026-07-27T10:18Z, i.e. **at master tip**. Vercel reporting READY is *not* the same
as the custom domain serving 200 — domain/alias health was **UNKNOWN** this window (no egress).

### 2.3 API

| Fact                              | Status      | Note                                                                 |
| --------------------------------- | ----------- | -------------------------------------------------------------------- |
| `api.vergeo5.com` `/healthz`      | **UNKNOWN** | egress denied (403 CONNECT) — not probed, not inferred               |
| Running image digest / `GIT_SHA`  | **UNKNOWN** | the API host is updated by a manual `docker pull` (`infra/redeploy-api.sh`), so a green GHCR build is **not** evidence of a deploy |
| GHCR image built at tip           | **VERIFIED**| "API image (GHCR)" **success** on `f85e8bd`                          |
| Last in-repo API health evidence  | 2026-07-23  | `docs/production-readiness/2026-07-23/live-probe-gap-report.md` — `/healthz` 200, `GIT_SHA=unknown`. **A 4-day-old probe is history, not current state.** |

### 2.4 CI (VERIFIED)

| Workflow                    | At `f85e8bd`      | Note                                                        |
| --------------------------- | ----------------- | ----------------------------------------------------------- |
| CI                          | **success**       | run 30257523743                                             |
| API image (GHCR)            | **success**       | run 30257523645                                             |
| E2E (Playwright · staging)  | **not run at tip**| last success at `29a7d94` (2026-07-27T06:04Z), two merges earlier |
| **Restore drill**           | **FAILURE**       | 4/4 scheduled runs failed (07-24, 07-25, 07-26, 07-27). Latest: `ERROR: dump implausibly small (636 bytes < 10240)` → manifest `status: failure`, `backup_too_small:636<10240` |

### 2.5 n8n (VERIFIED)

9 workflows on the instance: **7 active** — analytics retention, payment reconciliation crons,
embeddings cron, reservation sweeper, notification dispatch, operational nudges, admin digest;
**2 inactive** — *Vergeo5 — Database Backup*, *Vergeo5 — shared error alert*.

**Neither `waha-intake-sweeps.json` nor `waha-intake-digest.json` is present on the instance** — they
are committed under `infra/n8n/` and have not been imported. D35's "no active WAHA workflow" holds by
absence, which is stronger than "imported but inactive".

---

## 3. Current release gates

Status vocabulary: `PASS` · `FAIL` · `BLOCKED_EXTERNAL` · `NOT_RUN` · `UNKNOWN`. **Nothing here is
`PASS` because code merged.**

| ID       | Gate                                        | Status               | What is actually known                                                                                                                                      |
| -------- | ------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **RG-1** | Deployment / API health + migration-apply    | **FAIL (partial UNKNOWN)** | Frontends READY at tip (VERIFIED). API health/digest **UNKNOWN**. Live DB is 8 migrations behind repo (`0071` vs `0079`) — **VERIFIED FAIL**.        |
| **RG-2** | M17 F-V4 Cloudinary headroom + cost-guard drill | **NOT_RUN**       | F-V4 is unresolved by design (`clip-cost-runbook.md` §6). The §4 kill-switch drill has not been run — and cannot be, since `clip_spend_monthly` does not exist live. |
| **RG-3** | M18 pilot checklist Stage-1 + kill-switch drill | **NOT_RUN**       | `intake-pilot-checklist.md` sign-off table is empty. §1 pre-flight cannot be ticked: `0072`–`0075` unapplied, no flag row, no WAHA host, workflows not imported. |
| **RG-4** | Lenco sandbox S1–S6, KYC/escrow proof, legal F4 | **BLOCKED_EXTERNAL** | `payments`/`ledger_transactions`/`orders`/`kyc_records` all `0` (VERIFIED). F9b credentials and F4 counsel artifact absent — unchanged since 2026-07-20. |
| **RG-5** | n8n backup/restore + failure-alert proof     | **FAIL**             | Backup workflow **inactive**; shared error alert **inactive**; the self-contained restore drill has failed **4/4** scheduled runs on a reproducible dump-size error. |

**Aggregate: NO_GO** for sandbox-transaction beta, controlled real-money beta, and public launch.
RG-1 and RG-5 are hard failures on their own; RG-4 is externally blocked.

---

## 4. Operator verification steps (what this session could not do)

Each step names the command/surface and the artifact to record. None of these were performed here.

1. **API health + digest (RG-1).** From a host with egress:
   `curl -sS https://api.vergeo5.com/healthz` · `/readyz` · `/fingerprint`, and record `env`,
   `git_sha`, `supabase_project_ref`. If `git_sha` is `unknown`, the deploy is untraceable — fix that
   before promoting anything. `scripts/ops/verify_live.sh` automates the whole matrix.
2. **Domain-level frontend health (RG-1).** `GET https://www.vergeo5.com/en/health`,
   `https://vendor.vergeo5.com/en/health`, `https://admin.vergeo5.com/en/health` (admin should be
   Access-gated). Vercel READY ≠ domain healthy.
3. **Migration apply (RG-1).** Apply `0072`→`0079` **in order**, then re-run `list_migrations` and
   confirm the ledger tip is `0079`, and that `clips`, `clips_comments`, `waha_vendor_intake` now
   exist and read **false**.
4. **Cloudinary headroom (RG-2).** Confirm the account's video plan and eager-transcode credit
   headroom, record it against F-V4, then run `docs/ops/clip-cost-runbook.md` §4 in full — including
   step 3, the one that proves the feed stays shoppable when the switch trips.
5. **Intake Stage 1 (RG-3).** Work `docs/plan/intake-pilot-checklist.md` §1–§4 top to bottom on real
   pilot infrastructure, including NB-7 three-way number separation and NB-8 host isolation, and
   record the Stage-1 decision in the sign-off table.
6. **Money drills (RG-4).** F9b sandbox credentials → `docs/production-readiness/2026-07-22/money-drill-runbook.md`
   S1–S6 → attach the ledger evidence. Obtain the F4 counsel artifact.
7. **Backup/restore (RG-5).** Diagnose the `backup_too_small` failure in the restore drill (the
   drill's own dump step, not the DB), get one green run, then take and restore a real dump per
   `infra/n8n/backup-schedule.md`. Bind the WhatsApp credential and publish the shared error alert.

---

## 5. D35 binding contract (restated, unchanged)

The M18 lane is governed by **D35** (`docs/plan/00-decisions.md`), which narrowly amends D15. This
document changes nothing about it and repeats it so no downstream summary can soften it:

- **Inbound-only.** WAHA never sends. There is **no WAHA outbound acknowledgement** — not for
  confirmations, not for follow-ups. A follow-up is recorded as *data* on the intake record
  (`intake_sessions.pending_requests`) and rendered by the vendor app.
- **M18-P05 is the only reviewed listing handoff.** No earlier pebble creates, modifies or publishes
  `vendor_listings`; publication is M18-P06's audited admin act.
- **Canonical kill switch: `waha_vendor_intake`** (default `false`, admin-write, `config_audit`-logged).
  It is the first check in the ingestion path.
- **Pinned WAHA `2026.5.1` raw-body protocol:** fail-closed `X-Webhook-Hmac` computed over the **raw**
  body with `X-Webhook-Hmac-Algorithm: sha512`, plus replay controls, source-IP allowlist and TLS.
  A valid **SHA-256** signature is still refused — lane separation is asserted by test.
- Groups/broadcast, customer messaging, OTP, payments and moderation remain **forbidden** on this lane.

---

## 6. Related

- `docs/plan/00-status.md` — top summary (kept SHA-free by `services/api/tests/test_status_doc_truth.py`)
- `docs/production-readiness/2026-07-20/go-no-go-report.md` + `current-implementation-board.md` — 2026-07-20 snapshot, drift-annotated
- `docs/production-readiness/2026-07-23/live-probe-gap-report.md` — last in-repo live API evidence
- `docs/ops/clip-cost-runbook.md` · `docs/plan/intake-pilot-checklist.md` · `docs/ops/waha-vendor-intake.md`
- `scripts/ops/verify_live.sh` — the read-only probe matrix this session could not run
