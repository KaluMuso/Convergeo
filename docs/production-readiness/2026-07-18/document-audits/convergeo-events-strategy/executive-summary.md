# Executive Summary — Convergeo Events Strategy Document Audit

**Document:** Convergeo Events Strategy & Ticketing Architecture (April 2026)  
**Slug:** `convergeo-events-strategy`  
**Audit date:** 2026-07-18  
**Mode:** READ-ONLY reconciliation against live Vergeo5 (`dpadrlxukcjbewpqympu`)

## Classification

Primary: **requirements / policy / specification** (ticketing architecture, discovery, organiser tooling, fraud, phased Zambia catalogue).  
Secondary: master-data taxonomy expectations; operational money/ticket expectations (empty in prod).

## Status totals

| Status                 |  Count |
| ---------------------- | -----: |
| VERIFIED               |      9 |
| PARTIAL                |     30 |
| MISSING                |     10 |
| CONFLICT               |      3 |
| NOT_AUDITABLE          |      4 |
| **Total atomic facts** | **56** |

## Verdict

The platform has a **real events/ticketing schema and API/UI shell** aligned with much of the brief (Event / EventInstance / TicketType / Ticket, free RSVP, visibility/access codes, early-bird + group tiers, 60s HMAC QR + PIN fields, 6h transfer cutoff, Phase-1 category list, 5% ticket commission + 0% free events, escrow timing constants in code).

It does **not** yet have a **production-proven events commerce loop**: **0** events, **0** tickets, **0** payments/ledger rows, and **live n8n lacks** the repo’s event-release / tickets-issue / tickets-release automations.

### Does this document create a release blocker?

**Yes — for an events/ticketing go-live (paid or high-trust free at scale).**

Blockers tied to this document’s money/trust path:

1. Inactive production ticket issue + event escrow release automation (P0).
2. No live payment/ledger proof of event escrow (P0).
3. Organiser Tier-1 GMV fraud cap not evidenced (P0).
4. Refund/cancel matrix not proven live (P0).
5. FORCE RLS exceptions on ticket allocation/price-tier tables (P0 investigate).

**No — as a blocker for non-events catalogue demo** already characterized in the foundation baseline (demo products, `public_launch=false`). Many MISSING items are **explicit Phase 2/3** in the source (PWYW, private UX polish, international concerts, promo/affiliate) and should not be treated as launch defects for a Phase-1 events slice.

## Conflicts to resolve (product decisions)

- **multi_day** type in brief vs live **`standard` + `ends_at`**.
- Brief **Meilisearch** language vs locked **Postgres** search stack.

## Assumptions

- Only the Events Strategy PDF was audited in this directory (Business Pipelines PDF excluded).
- n8n MCP list of 2 workflows is the complete live set.
- Code/OpenAPI presence ⇒ PARTIAL, never VERIFIED production behavior.
- No records were created or modified.

## Artifact index

| File                               | Purpose                           |
| ---------------------------------- | --------------------------------- |
| `source-document.md`               | Metadata + extracted PDF text     |
| `extracted-facts.json`             | 56 atomic facts with statuses     |
| `reconciliation-matrix.md`         | Full human matrix + entity map    |
| `missing-and-conflicting-items.md` | Gap taxonomy a–f                  |
| `safe-query-log.md`                | Read-only probe log (counts only) |
| `remediation-backlog.md`           | BL-001+ recommended fixes         |
| `executive-summary.md`             | This file                         |
