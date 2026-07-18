# Executive Summary — Strategic Foundation Questionnaire (April 2026) audit

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY (no production changes) · **Auditor role:** Document-to-Production Data Reconciliation
**Document:** Convergeo — Strategic Foundation Questionnaire & Business Review v1.0 (image-only PDF, 24 pp)
**Classification:** Requirements / policy / specification (business review + 15 red-team scenarios + 75-question questionnaire)

---

## Verdict

This document is a **strategic planning input, not a data record** — it names no customers, vendors, orders, or payments, so there is no record-matching to perform. Its audit value is reconciling its **claims, recommendations, and red-team "prevention" requirements** against the live platform.

**Two facts frame everything:**
1. **All 75 questionnaire questions are blank** in the artifact. The decisions were made elsewhere — the **28 locked decisions** in `docs/plan/00-decisions.md` (D1–D28). This artifact is the question set, not the answer set.
2. The live platform is a **demo marketplace with zero money operations** (0 payments / 0 ledger / 0 payouts / 0 tickets). So most of the document's commerce/trust requirements are **designed but unproven** rather than present or absent.

**Does this document create a release blocker?** **Yes — but they are pre-existing platform blockers this document independently re-confirms, not new record defects.** The document's own non-negotiables — escrow from launch (RT#5), mobile-money-first (RT#1), instant/automated settlement (RT#9), regulatory compliance (RT#12) — all map to platform capabilities that exist in **code/schema only** and are **not live-proven**, plus a standing RBAC role-hook gap. These are **P0 until VERIFIED** per the audit contract. This document must **not** be treated as clearing any of them.

---

## Status counts (79 atomic facts)

| Status | Count | Share |
| --- | --- | --- |
| **VERIFIED** | 10 | 13% |
| **PARTIAL** | 47 | 59% |
| **MISSING** | 7 | 9% |
| **CONFLICT** | 8 | 10% |
| **NOT_AUDITABLE** | 7 | 9% |

The **59% PARTIAL** rate is the signature of a live-but-pre-revenue demo platform: the architecture is real and largely matches the plan, but the money/trust/automation paths have no operational data to prove them.

### What is genuinely VERIFIED (live strengths matching the doc)
3-app Customer/Vendor/Admin topology · Next.js 15 frontends · shared FastAPI backend + monorepo · Postgres FTS + pgvector search · Cloudinary media · ZMW-only ngwee money model · phone-OTP auth · PWA · canonical-product comparison model · no own-gateway (Lenco abstraction).

### Headline CONFLICTS (document vs ratified reality)
- **Backend:** doc recommends Django+PostgreSQL; platform is FastAPI+Supabase (D18 — deliberate, documented). *Low severity.*
- **Launch languages:** red-team says launch EN+Bemba+Nyanja; platform launches English-only + scaffolding (D27); `translation_overrides` migration unapplied. *Medium.*
- **Demo catalogue exposure:** 134 demo listings + demo images served by the **public** catalog (`total=134`), contradicting D25's "demo excluded from public search." *Medium (P1).*
- **Cross-border data model:** red-team says build the multi-currency seam now; platform is single-currency ZMW. *Medium.*
- **Payment/DPO & Celery:** doc assumes Lenco/DPO redundancy and Celery+n8n; platform is Lenco-only and n8n+outbox. *Low.*
- **Process:** the 75-question form is blank; approvals live in `00-decisions.md`. *Low.*

### MISSING (features the doc requires that don't exist)
Escrow auto-release workflow · ticket-issuance workflow · Yango/courier API integration · retail-chain pickup network · vendor financing · super-app utility (airtime/bills) · AR try-on (correctly deferred).

---

## Release-blocker call (P0 / P1)

| Priority | Count | Blockers (this document's lens) |
| --- | --- | --- |
| **P0** | **5** | SFQ-01 prepaid→ledger posting unproven · SFQ-02 escrow auto-release missing · SFQ-03 ticket issuance missing · SFQ-04 legal/DPA/NPS-Act sign-off pending (F4) · SFQ-05 role-hook / admin-RBAC provisioning gap |
| **P1** | **8** | SFQ-06 migration drift (0051/0053–0055) · SFQ-07 seller CTA env · SFQ-08 demo catalogue public · SFQ-09 vernacular launch · SFQ-10 observability · SFQ-11 backups · SFQ-12 mobile-money proof · SFQ-13 real vendor pre-onboarding |
| P2 | 7 | Multi-currency seam, courier API, WhatsApp commerce, task-runner ADR, CI hardening, roadmap features, Q→D mapping |

**Bottom line:** The plan and the build are well-aligned architecturally, and nothing in this document reveals a new hidden data defect. But every money-and-trust requirement the document treats as non-negotiable is currently **PARTIAL/MISSING and live-unproven**. Until SFQ-01…05 are **VERIFIED in a sandbox**, this document does **not** clear the platform for real-money launch — it re-confirms the P0 blockers already on record (foundation R2/R3/R4/R8).

---

## Assumptions & caveats (stated explicitly)

1. **Blank = undecided-in-this-artifact.** I treat unselected options as "not answered here" and use `00-decisions.md` (rank-4 documentation) only as *intent context*, never as production proof.
2. **Same-day foundation reuse.** Supabase SQL and `*.vergeo5.com` HTTP were blocked by org egress policy this session; DB/catalogue/RLS aggregates are cited from the foundation snapshot captured ~3 h earlier the same day, and labelled as such.
3. **No compliance/settlement inference.** Legal compliance (RT#12) and payment settlement (RT#5/#9) are labelled NOT_AUDITABLE/PARTIAL — never assumed satisfied.
4. **No records created, no writes, no workflow activation, no payments.** All coverage is from read-only listing/aggregate probes.
5. **Cloudinary 60 vs DB 134 demo images** is image reuse across listings, not a conflict.
