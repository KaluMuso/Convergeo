# Go / No-Go report — 2026-07-20 (Prompt 12)

**Audit time (UTC):** 2026-07-20T15:30Z  
**Auditor:** Cursor Cloud agent (evidence-first)  
**Supersedes:** earlier readiness % claims where this report cites newer live probes  
**Companions:** `current-implementation-board.md`, `release-gates.md`, programme evidence on PRs #376–#380 (not all merged to master at audit tip)

---

## Final recommendation

# **NO_GO**

Not eligible for sandbox-transaction beta, controlled real-money beta, or public launch.  
**Nearest next level:** `BROWSE_ONLY_CONTROLLED_BETA` — **blocked** (see promotion blockers below).

Hard P0 failures are **not** averaged away.

---

## 1. Fingerprint (verified this audit)

| #   | Check              | Result                                                   | Evidence                                                                   |
| --- | ------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | Master SHA         | `d9839db349887ab48a52c18546e05961a62498d6`               | `git rev-parse origin/master` — Merge #369 customer commerce discovery     |
| 2   | Customer prod SHA  | `cde40bf32763d14511deb72c59c1a7586867f93e`               | `GET https://www.vergeo5.com/en/health` → 200; Vercel prod `dpl_6Pgevsi…`  |
| 3   | Vendor prod SHA    | `5a4668a10291b3c381613975139431658c3c5be4`               | Vercel prod `dpl_3qg4H35…`; `/en/health` → 200 after redirect              |
| 4   | Admin prod SHA     | `2f9971110797ca722dfb6a68e73a66955e0f714c`               | Vercel prod `dpl_298135…`; unauth `/en/health` → **302** Cloudflare Access |
| 5   | API digest         | **UNKNOWN**                                              | `GET https://api.vergeo5.com/{healthz,readyz,fingerprint}` → **HTTP 502**  |
| 6   | Live migration tip | `0063_revoke_execute_review_reply_guards`                | Supabase `dpadrlxukcjbewpqympu` `schema_migrations` DESC                   |
| 7   | Repo migration tip | `0064_force_rls_launch_tables.sql`                       | `supabase/migrations/` on master                                           |
| 8   | Collision          | Live `0063` = revoke; repo `0063` = `refunds.source_key` | Column `refunds.source_key` **absent** live                                |
| 9   | `0056` KYC         | **Applied**                                              | Migration name `0056_kyc_integrity` present                                |
| 10  | `0064` FORCE RLS   | **Not applied**                                          | `has_0064_force_rls=false`; ticket tiers FORCE still false                 |

### RLS / FORCE RLS (live sample)

| Table                                                                                                    | RLS  | FORCE RLS |
| -------------------------------------------------------------------------------------------------------- | ---- | --------- |
| orders, payments, ledger_*, refunds, payouts, vendors, vendor_listings, kyc_records, user_roles, tickets | true | true      |
| ticket_type_instances, ticket_type_price_tiers, product_relations                                        | true | **false** |

### Money / catalogue counts (live)

| Metric                                                          | Count     |
| --------------------------------------------------------------- | --------- |
| payments / ledger_transactions / orders / refunds / kyc_records | **0**     |
| products / vendor_listings                                      | 150 / 134 |

### Flags

| Flag                               | Enabled                                                                     |
| ---------------------------------- | --------------------------------------------------------------------------- |
| `public_launch`                    | **false**                                                                   |
| `zamtel_collections`               | **false**                                                                   |
| Dedicated payment kill-switch flag | **not present** as named row (fail-closed via API down + empty money plane) |

### n8n (live MCP `search_workflows`)

| Workflow                               | Active                                                       |
| -------------------------------------- | ------------------------------------------------------------ |
| Vergeo5 — notification dispatch        | **false**                                                    |
| Vergeo5 — payment reconciliation crons | **false**                                                    |
| Vergeo5 — shared error alert           | **false**                                                    |
| Count                                  | **3** live (19 committed JSON on master; backup.json absent) |

### Frontend route probes (customer)

| Path                                                             | HTTP                         | localhost leak |
| ---------------------------------------------------------------- | ---------------------------- | -------------- |
| `/en`, `/en/sell`, `/en/categories`, `/en/compare`, `/en/search` | 200                          | 0              |
| `/en/sell` CTA                                                   | disabled invite-only honesty | n/a            |

---

## 2. Programme evidence inventory (2026-07-20)

| Prompt                  | Artifact / PR                            | Verdict used here                                                    |
| ----------------------- | ---------------------------------------- | -------------------------------------------------------------------- |
| 7 n8n fleet             | PR #376 `n8n-fleet-import-verify.md`     | Fail-closed unpublished erroring ticks; S4/G5/G21 FAIL               |
| 8 Lenco sandbox         | PR #377 `lenco-sandbox-money-drill.md`   | **BLOCKED_EXTERNAL** (F9b + API 502 + tip mismatch)                  |
| 9 Observability         | PR #378 `observability-live-evidence.md` | G6 FAIL; Sentry create 403; uptime NOT_AUDITABLE                     |
| 10 Ops drills           | PR #379 `ops-drills/`                    | Restore CONDITIONAL (drill dump); rollback/load NOT_RUN → G7/G9 FAIL |
| 11 Code-completion plan | PR #380 `code-completion-programme.md`   | Plan only — no gate clearance                                        |

**Note:** Master tip `d9839db` does **not** yet include #376–#380. Audit treats those packs as programme evidence; live probes above reconfirm the same blockers.

---

## 3. Gate scorecard (S + G)

Allowed statuses only: `PASS` · `FAIL` · `CONDITIONAL` · `BLOCKED_EXTERNAL` · `NOT_APPLICABLE`.

### Staging gates

| ID     | Status               | Evidence / reason                                                                           |
| ------ | -------------------- | ------------------------------------------------------------------------------------------- |
| **S0** | **FAIL**             | No dedicated staging schema plane; live tip ≠ repo tip (`0063` collision); `0064` unapplied |
| **S1** | **BLOCKED_EXTERNAL** | F9b Lenco sandbox creds unavailable; API 502 — Prompt 8                                     |
| **S2** | **BLOCKED_EXTERNAL** | Same as S1                                                                                  |
| **S3** | **FAIL**             | Release drill not run; money-moving n8n unpublished; CODE_COMPLETE only historically        |
| **S4** | **FAIL**             | No release/tickets workflows active; 0/3 live workflows active                              |
| **S5** | **FAIL**             | `0056` applied but KYC lifecycle drill not executed (`kyc_records=0`)                       |
| **S6** | **FAIL**             | False-success E2E CODE on PR #370 — not staging-verified against live/sandbox               |
| **S7** | **FAIL**             | No written UAT pack attached                                                                |

### P0 production gates

| ID     | Status               | Evidence / reason                                                                                                                      |
| ------ | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **G0** | **FAIL**             | FORCE RLS false on ticket tiers + `product_relations`; repo `0064` unapplied; migration numbering collision open                       |
| **G1** | **FAIL**             | API healthz/readyz **502**; frontend prod SHAs behind master tip; admin Access OK                                                      |
| **G2** | **CONDITIONAL**      | **PASS** aspect: zero `localhost:3001/8000` on probed HTML. Seller CTA intentionally disabled (invite honesty) — not a live vendor CTA |
| **G3** | **FAIL**             | No sandbox/live ledger posts; `payments=0`, `ledger_transactions=0`; Prompt 8 blocked                                                  |
| **G4** | **FAIL**             | No staging E2E false-success proof attached to this tip                                                                                |
| **G5** | **FAIL**             | Escrow release / tickets / dispatch not active-healthy; fail-closed only                                                               |
| **G6** | **BLOCKED_EXTERNAL** | No Vergeo5 Sentry projects (create 403); uptime NOT_AUDITABLE — Prompt 9                                                               |
| **G7** | **FAIL**             | No approved backup workflow/artifact; restore CONDITIONAL on local-ci drill dump only — Prompt 10                                      |
| **G8** | **FAIL**             | `secret-scan` / several CI steps `continue-on-error`; branch protection NOT_AUDITABLE                                                  |
| **G9** | **FAIL**             | API digest UNKNOWN; rollback drill NOT_RUN; DB tip drift — Prompt 10                                                                   |

### P1 gates

| ID      | Status               | Evidence / reason                                                                                                              |
| ------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **G10** | **FAIL**             | `/en/sell` CTA disabled (invite-only) — not a live seller CTA to vendor prod                                                   |
| **G11** | **CONDITIONAL**      | Demo exclusion CODE on master path (#368 / admin prod includes merge); live API 502 blocks PRODUCTION_VERIFIED discovery probe |
| **G12** | **CONDITIONAL**      | `0056` applied live; no orphan/live KYC drill evidence                                                                         |
| **G13** | **BLOCKED_EXTERNAL** | F4 counsel written sign-off absent                                                                                             |
| **G14** | **CONDITIONAL**      | `zamtel_collections=false` (safe default); F9a decision still open                                                             |
| **G15** | **FAIL**             | Admin RBAC decision not closed in decisions corpus                                                                             |
| **G16** | **FAIL**             | Staging UAT pack absent                                                                                                        |
| **G17** | **FAIL**             | Panel honesty not PRODUCTION_VERIFIED at master tip parity                                                                     |

### P2 (tracked)

| ID      | Status             | Notes                                                        |
| ------- | ------------------ | ------------------------------------------------------------ |
| **G18** | **FAIL**           | bem/nya 8/17 namespaces; noindex; native review open         |
| **G19** | **FAIL**           | Launch LH floors not PRODUCTION_VERIFIED                     |
| **G20** | **NOT_APPLICABLE** | Auth advisor item — not re-probed this audit (no PASS claim) |
| **G21** | **FAIL**           | Lifecycle n8n not imported/activated                         |
| **G22** | **FAIL**           | Doc SoT banners incomplete (CCP-08)                          |

---

## 4. Founder / legal / credentials

| Gate              | Status                          | Notes                                                   |
| ----------------- | ------------------------------- | ------------------------------------------------------- |
| F1 Domain         | **PASS**                        | vergeo5.com (checklist)                                 |
| F2 PACRA + TPIN   | **FAIL**                        | Unchecked                                               |
| F3 Lenco docs     | **CONDITIONAL**                 | Distilled API docs present; founder confirm             |
| F4 Counsel        | **BLOCKED_EXTERNAL**            | No written artifact                                     |
| F5 WhatsApp Cloud | **FAIL** / **BLOCKED_EXTERNAL** | Templates/creds not proven live                         |
| F6 Courier MOUs   | **NOT_APPLICABLE**              | Post-beta acceptable                                    |
| F7 Design HTMLs   | **FAIL**                        | 6 missing (SOURCES.md) — checklist still says 7 (stale) |
| F8 COD cap        | **CONDITIONAL**                 | `cod_cap_ngwee=50000` live                              |
| F9a Zamtel        | **CONDITIONAL**                 | Flag false                                              |
| F9b Lenco creds   | **BLOCKED_EXTERNAL**            | Prompt 8                                                |
| Legal G13         | **BLOCKED_EXTERNAL**            | Same as F4                                              |

---

## 5. Percentages (separate lenses — do not blend into one “ready” number)

| Lens                             | %        | Method / caveat                                                                                  |
| -------------------------------- | -------- | ------------------------------------------------------------------------------------------------ |
| **Build representation**         | **~92%** | Code vs v1 docs; M17/deferred scope excluded; matches ~90–93% prior                              |
| **Deployed representation**      | **~45%** | Frontends live but **behind** tip; API down/unknown digest; DB tip collision; FORCE RLS residual |
| **Operational readiness**        | **~22%** | n8n fail-closed; no Sentry/uptime proof; no approved backup/restore/rollback/load                |
| **Real-money launch readiness**  | **~8%**  | Hard FAIL on S1–S6 + G3–G5 + F4/F9b — **not averaged up**                                        |
| **Browse-only beta readiness**   | **~35%** | Marketing shells + flags safe, but **API 502** breaks dynamic catalogue/search truth             |
| **Full public-launch readiness** | **~5%**  | Requires real-money GO + G10–G17                                                                 |

Any single hard P0 FAIL keeps real-money and public launch at **NO_GO** regardless of build %.

---

## 6. Promotion blockers

### Current → `BROWSE_ONLY_CONTROLLED_BETA`

Must clear at minimum:

1. **G1** — API `healthz`/`readyz` 200 + recorded digest
2. **G11** — live discovery probe proves demo exclusion (or labelled demo) with API up
3. **G9** (partial) — intentional frontend SHAs recorded at promote time; `public_launch=false` held
4. Founder eyes-on invite cohort process (`beta_invites`)

Optional soft: G2 remains CONDITIONAL while sell CTA stays invite-disabled (acceptable for browse-only).

### `BROWSE_ONLY` → `SANDBOX_TRANSACTION_BETA`

1. **S0–S4, S6** PASS/STAGING_VERIFIED
2. **S1/S2** — F9b sandbox creds + successful MoMo/card→ledger drills
3. **G3/G4/G5** — ledger + false-success + workflow ticks
4. Tip reconcile: live `refunds.source_key` + repo/live `0063` collision closed

### `SANDBOX` → `CONTROLLED_REAL_MONEY_BETA`

1. All P0 **G0–G9** PASS
2. **G13 / F4** counsel PASS
3. **F9b** production creds + kill-switch runbook
4. S5 KYC live drill

### `CONTROLLED_REAL_MONEY` → `PUBLIC_LAUNCH_GO`

1. **G10–G17** PASS
2. Explicit `public_launch` flip authorisation
3. G6/G7/G9 production-hardened

---

## 7. What is safe today

- Keep **`public_launch=false`** and **`zamtel_collections=false`**.
- Keep money-moving n8n **unpublished** while API returns 502.
- Customer marketing / invite-only sell honesty pages respond 200 without localhost leaks.
- Do **not** enable production collections or open seller self-serve.

---

## 8. Signature block

| Role            | Name                   | Decision  | Date       |
| --------------- | ---------------------- | --------- | ---------- |
| Auditor (agent) | Cursor Cloud Prompt 12 | **NO_GO** | 2026-07-20 |
| Founder         | _pending_              |           |            |
| Counsel         | _pending_              |           |            |

_Evidence links in §1–§3 are authoritative for this date. Do not treat unmerged programme PRs as master deploy truth._
