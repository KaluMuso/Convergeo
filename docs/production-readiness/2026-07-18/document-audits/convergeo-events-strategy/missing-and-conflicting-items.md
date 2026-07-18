# Missing and Conflicting Items — Convergeo Events Strategy

**Audit date:** 2026-07-18 · **Slug:** `convergeo-events-strategy`

## a. Missing production records

| ID        | Item                                                  | Evidence                          | Impact                          |
| --------- | ----------------------------------------------------- | --------------------------------- | ------------------------------- |
| F047/F050 | Published events / instances / ticket types / tickets | Counts all **0**                  | Events tab empty; no commerce   |
| F050      | Payments / ledger transactions for tickets            | **0** payments, **0** ledger txns | Escrow/settlement unproven      |
| F033      | Ticket transfers                                      | `ticket_transfers` **0**          | Transfer path unproven          |
| F035      | Refunds / disputes for events                         | `refunds`/`disputes` **0**        | Policy matrix unproven          |
| F036/F037 | KYC records for organisers                            | `kyc_records` **0**               | Tiered organiser trust unproven |

**Note:** Absence of Phase-2/3 catalogue rows is expected roadmap state, not a data-import defect. Do **not** seed production from this audit.

## b. Missing fields / schema support

| ID   | Item                                  | Evidence                                           | Notes                                       |
| ---- | ------------------------------------- | -------------------------------------------------- | ------------------------------------------- |
| F006 | `multi_day` event_type enum value     | CHECK is `standard\|recurring\|free_rsvp\|private` | CONFLICT with brief; duration via `ends_at` |
| F016 | Pay-what-you-want pricing             | No kind/columns                                    | Explicit Phase 3 in source                  |
| F017 | Venue hard ceiling + held-comps pools | No venue_capacity / comps tables                   | Oversell guard is per-tier/instance only    |
| F019 | Absorb vs pass-through fee mode       | No fee_mode column                                 | Organiser commercial UX                     |
| F010 | First-class `perks` on TicketType     | Not a column                                       | May use name/description                    |
| F039 | Co-organiser roles tables             | `event_organiser_roles` absent                     | Owner-only today                            |
| F040 | Promo codes / affiliate tables        | `promo_codes` / `event_affiliates` absent          | Growth tools                                |
| F043 | High-value ID-match toggle            | No column                                          | Phase 2 concerts                            |

## c. Configuration / workflow gaps

| ID             | Item                                                                        | Evidence                                                                                               | Priority                       |
| -------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------ |
| F020/F021/F050 | Live n8n **event-release**, **tickets-issue**, **tickets-release** inactive | n8n search returned only dispatch + payment reconciliation active; repo JSON exists under `infra/n8n/` | **P0** before paid tickets     |
| F044           | Pre-event verification call ops (>K100k)                                    | No n8n/ops workflow                                                                                    | P2 (Phase 2/3)                 |
| F036           | Tier-1 GMV cap (~K20,000)                                                   | Not found in live platform_config/commission                                                           | **P0** investigate before paid |
| F056           | `public_launch=false`                                                       | All feature flags false                                                                                | Expected invite gate           |

## d. UI / customer / vendor / admin gaps

| ID             | Item                                                     | Evidence                                           |
| -------------- | -------------------------------------------------------- | -------------------------------------------------- |
| F022           | When lenses Next Week / Next Month                       | Only tonight / this_weekend / all                  |
| F024           | Where city / near-me lens                                | Not on public `/events` payload                    |
| F025           | “Selling fast” badge                                     | Absent in `/en/events` HTML probe                  |
| F026           | Homepage default Tonight+Weekend                         | Home lacked tonight/weekend strings                |
| F027           | Full month calendar route                                | `/en/calendar` **404** (chips only on events page) |
| F030           | Offline scanner secret cache                             | Vendor scan offline = cannot verify                |
| F039           | Door/Manager roles UX                                    | Missing with schema                                |
| F018/F041/F055 | Checkout fee breakdown, organiser stats depth, wallet QR | Auth-gated — see NOT_AUDITABLE                     |

## e. Conflicting data / specifications

| ID   | Conflict         | Side A (document)               | Side B (production)                                                      |
| ---- | ---------------- | ------------------------------- | ------------------------------------------------------------------------ |
| F006 | Event type model | 5 types including **multi_day** | 4 types; **standard** replaces single; multi-day via `ends_at`           |
| F025 | Search stack     | Meilisearch + pgvector          | Postgres FTS + pg_trgm + pgvector (locked stack)                         |
| F051 | FORCE RLS        | Implied uniform hard RLS        | `ticket_type_instances` & `ticket_type_price_tiers` **rls_forced=false** |

## f. Access / evidence limitations

| Need                                             | Why                                                       | Blocks                      |
| ------------------------------------------------ | --------------------------------------------------------- | --------------------------- |
| Authenticated customer session                   | Wallet QR, checkout fee breakdown, transfer claim UX      | F018, F055                  |
| Authenticated vendor/organiser session           | Create/publish event, scanner success path, stats metrics | F034, F038, F041            |
| Staging/prod-safe issued ticket + scanner device | Dynamic QR/PIN/first-scan/offline                         | F003, F029–F032, F042       |
| Confirmation of intentional FORCE RLS exceptions | Security sign-off                                         | F051                        |
| City-guide route inventory                       | Q52 integration claim                                     | F028                        |
| Lenco dashboard / real payment                   | Settlement truth beyond code                              | F020/F021/F050 money claims |

Assumptions: n8n MCP listing is complete; operator SQL ≠ end-user RLS view; code≠production behavior.
