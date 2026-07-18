# Remediation Backlog — Strategic Foundation Questionnaire (April 2026)

**Audit date:** 2026-07-18 · Derived from `reconciliation-matrix.md` + `missing-and-conflicting-items.md`.
**Scope note:** This session makes **no production changes**. Every item is a *recommended* controlled remediation. Priorities: **P0** = money/trust/security/regulatory release-blocker; **P1** = launch-quality; **P2** = roadmap/scope hygiene.

Because the source is a strategy document, several items overlap the foundation's existing risk register (R1–R8). Where they do, the register ID is cited so this backlog does not double-count — it re-frames those risks against *this document's specific requirements*.

| ID | Priority | Affected panel/service | Evidence | Proposed fix (controlled) | Acceptance criteria | Dependencies | Suggested owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SFQ-01 | **P0** | Payments / API (ledger) | F044/F074/F111; `ledger_transactions`=0; prepaid-posting code merged PR #274 but unproven | In a **sandbox**, drive one MoMo + one card prepaid checkout; assert `CHARGE_RECEIVED`/`ESCROW_HOLD` legs post and balance | Sandbox order shows balanced double-entry escrow legs; fixture captured as VERIFIED evidence | Lenco sandbox creds (env); no prod payment | Payments / M08 |
| SFQ-02 | **P0** | Ops / n8n · Payments | F016/F044/RT#5; live n8n has no `release-job` | Import + activate escrow **auto-release** workflow with internal token; prove one release tick on a sandbox held order | Held funds transition to release→payout on delivery-confirm/48h; audit log entry present | SFQ-01; `INTERNAL_RELEASE_JOB_TOKEN` | Ops / M13–M14 |
| SFQ-03 | **P0** | Ops / n8n · Events | F014/F092/Applause#5; no `tickets-issue` workflow; `tickets`=0 | Import + activate ticket-issuance workflow; prove one issuance after a sandbox ticket order | Paid ticket order yields an issued ticket (dynamic-QR) + notification | SFQ-01; `INTERNAL_TICKETS_ISSUE_TOKEN` | Ops / M13 |
| SFQ-04 | **P0** | Legal / Compliance | F051/F096/RT#12; F4 counsel review pending; DPA/NPS-Act not verifiable | Complete Zambian counsel review of Lenco-held escrow (NPS Act 2026) + confirm Data Protection Act (2021) posture **before real-money launch** | Written legal sign-off recorded; compliance gates checked; NOT inferred | External counsel (F4); founder | Founder / Legal |
| SFQ-05 | **P0** | Security / RBAC (Admin) | access-and-rls §3.5; `0051_custom_access_token_role_hook` **not applied**; `user_roles` no client policies | Decide + apply role hook (then enable in Auth dashboard) **or** document manual-grant posture; verify admin role isolation test | Role provisioning path documented + tested; edge gates match `user_roles`; RLS admin-isolation test green | DB migration window; Auth dashboard | Founder / Platform |
| SFQ-06 | P1 | DB / migrations | F047/F079; live at ≤0050(+0052); repo at 0055 | Reconcile & apply `0051`,`0053`,`0054`,`0055` (or document why not) in a controlled window; fix 0052 version-key skew | Live applied set == repo tip (or documented divergence); `translation_overrides`/`services.bookable` present | Backup (SFQ-11); review | Ops / DB |
| SFQ-07 | P1 | Customer web (acquisition) | F031/R1; `/sell` CTAs disabled; `NEXT_PUBLIC_VENDOR_APP_URL` likely unset | Set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer`; redeploy; re-verify CTA href | `/sell` CTA links to live vendor app; no "temporarily unavailable" copy | Vercel env access | Founder / Vercel |
| SFQ-08 | P1 | Catalogue / merchandising | F110/R5/E6; 134 demo listings + demo images public (`total=134`); D25 intended exclusion | Gate demo behind `public_launch=false` in public search, **or** label as demo, **or** replace with real vendors before real-money positioning | Public catalog excludes/【labels demo; SEO not polluted with demo | Vendor onboarding (SFQ-13) | Founder / Merch |
| SFQ-09 | P1 | i18n (all apps) | F047/F079/E3/RT#8; launch English-only; 0053 unapplied | Apply `translation_overrides`; prioritize Bemba + Nyanja copy for core buyer flows; keep checkout/legal human-reviewed | Bemba/Nyanja available for browse/cart; override table live | SFQ-06; human translators (D27) | Founder / i18n |
| SFQ-10 | P1 | Observability | F049/R4; no Vergeo5 Sentry projects; analytics 0 rows | Create Sentry projects + wire DSNs; verify analytics streams populate after PRs #275–277; configure UptimeRobot | Test error visible in Sentry; non-zero analytics after traffic; uptime monitor active | DSN env; post-wiring traffic | Founder / M16 |
| SFQ-11 | P1 | Backups / DR | c-table/R3; backup workflow absent in n8n | Import backup workflow (Supabase dump → OCI Object Storage) or prove existing host cron; document RPO/RTO | One successful backup artifact verified; restore runbook validated | OCI storage creds | Ops / M10 |
| SFQ-12 | P1 | Payments (mobile money) | F040/RT#1/Q20; `zamtel_collections`=false; no USSD | Confirm MTN/Airtel MoMo push works (SFQ-01); decide Zamtel timeline (F9a); scope USSD fallback | MoMo push proven; Zamtel plan recorded; USSD decision documented | SFQ-01; Lenco/Zamtel | Payments / Founder |
| SFQ-13 | P1 | Vendor acquisition | F054/RT#15; 3 demo vendors, 0 real; `public_launch`=false | Pre-onboard 50–100 real vendors before public launch; verify onboarding/KYC flow live | ≥50 real vendors with listings; KYC flow exercised end-to-end | SFQ-07; onboarding UX | Founder / BD |
| SFQ-14 | P2 | Data model (payments) | F050/E4/RT#11; ZMW-only, no currency seam | Decide now: add a currency dimension to money tables **or** accept a future migration; record decision | Explicit ADR on multi-currency seam; no silent lock-out | Product decision | Founder / Arch |
| SFQ-15 | P2 | Delivery | F013/F090/E5/RT#4; no courier API; no pickup network | Backlog Yango/Bolt courier API (Phase 2) + retail-chain pickup partnerships; reconcile Applause#4 vs D16 | Courier API design doc + partnership shortlist; applause claim corrected | Partnerships (F6) | Ops / BD |
| SFQ-16 | P2 | WhatsApp / channels | F041/RT#2; WhatsApp is notification-only | Scope WhatsApp Business commerce (order/track/support) on official Cloud API | Design doc for WhatsApp order flow; no WAHA | D15; Meta setup (F5) | Founder / M15 |
| SFQ-17 | P2 | Background tasks | F070/E8/Q18; no Celery/Redis queue | Confirm whether Celery is intended (Q18-C rec) or intentionally replaced by outbox+n8n; record decision | ADR on task-runner choice | Arch review | Platform |
| SFQ-18 | P2 | CI / branch protection | R7; `secret-scan` `continue-on-error:true`; branch protection not verifiable | Make secret-scan blocking; align `docs/ops/ci.md`; confirm GitHub branch-protection UI | Secret-scan blocking on master; docs match YAML | Repo admin | Founder / Platform |
| SFQ-19 | P2 | Roadmap features | F052/F053/F102/Q69/Q70; financing, super-app, AR, visual/voice search absent | Track as explicit roadmap items with phase tags; do not market as present | Backlog entries with phase + owner | Product | Founder |
| SFQ-20 | P2 | Process / decisions | F002/E7; questionnaire blank; answers in `00-decisions.md` | Add a Q→D mapping table linking each of the 75 questions to its locked decision (or "OPEN") | 75-row mapping committed; open items flagged | `00-decisions.md` | Founder |

---

## Rollup

| Priority | Count | Items |
| --- | --- | --- |
| **P0** | 5 | SFQ-01, SFQ-02, SFQ-03, SFQ-04, SFQ-05 |
| **P1** | 8 | SFQ-06 … SFQ-13 |
| **P2** | 7 | SFQ-14 … SFQ-20 |

**Interpretation:** No P0 originates from a *data-record* discrepancy (this is a strategy document). All P0s are money/trust/security/regulatory items where the document's stated requirements (escrow from launch, mobile-money-first, ticketing, compliance) meet a platform that has the **design but no live proof** — plus one standing RBAC/role-hook gap. These mirror foundation risks R2/R3/R4/R8 and are release-blockers until VERIFIED.
