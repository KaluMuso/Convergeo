# Blockers — Evidence-Backed (Batch 0)

**Date:** 2026-08-06  
**Aggregate launch posture:** **NO_GO** (consistent with `docs/plan/00-status.md`)

Blockers are **not repaired in Batch 0** — recorded for programme visibility.

---

## P0 — Blocks trustworthy audit or launch

| ID          | Blocker                                                                          | Evidence                                                            | Owner     |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------- | --------- |
| **BLK-001** | Production DB migration tip unknown vs Git (`0093+`, clips/intake `0072`–`0079`) | 96 migrations in Git; status doc cites prod at `0071` (2026-08-01)  | Ops/DB    |
| **BLK-002** | API production health unverified this programme session                          | No egress probe; dated docs mixed (502 resolved then unknown)       | Ops       |
| **BLK-003** | RLS CI matrix may be false-green (RG-6)                                          | `00-status.md` 2026-08-02: 1125 failures, `continue-on-error: true` | Eng       |
| **BLK-004** | Canonical Requirements Registry not in repository                                | Grep found no CAN-* / registry file                                 | Programme |
| **BLK-005** | Zero money rows exercised on any environment                                     | status doc: payments/orders/ledger all 0 (verified 2026-08-01)      | Ops + F9b |
| **BLK-006** | n8n money/backup workflows partially imported                                    | status doc: 15/24 never imported; backup inactive                   | Ops       |
| **BLK-007** | F4 legal counsel sign-off absent                                                 | Pre real-money gate per D14                                         | Founder   |

---

## P1 — Significant risk, not sole launch blockers

| ID              | Blocker                                                                                 | Evidence                                                            |
| --------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| **BLK-101**     | B2B cart read-path may not re-derive wholesale eligibility                              | `00-status.md` G3: `_build_cart_response` reads stored `cart_items` |
| **BLK-102**     | Sentry projects may not exist for all apps                                              | `observability-live-evidence.md` 2026-07-20                         |
| ~~**BLK-103**~~ | ~~Triple `0093_*` migration prefix~~ — **resolved** `0093`–`0095` renumber (2026-08-06) | Was blocking CI migration replay / RLS / perf                       |
| **BLK-104**     | Custom access token hook disabled                                                       | `0051` SQL vs commented hook in `config.toml`                       |
| **BLK-105**     | `supabase/config.toml` Postgres 15 vs cloud 16                                          | Version mismatch in config                                          |

---

## Safety gates (must remain enforced)

| Gate               | Mechanism                                       | Default                   |
| ------------------ | ----------------------------------------------- | ------------------------- |
| Online payments    | `PAYMENTS_ENABLED`, `PAYMENTS_ALLOW_PRODUCTION` | OFF                       |
| Payouts            | `PAYOUTS_ENABLED`, `STAGING_ALLOW_PAYOUTS`      | OFF                       |
| Public marketplace | `public_launch` feature flag                    | false                     |
| WAHA intake        | `waha_vendor_intake` flag                       | false                     |
| Clips              | `clips`, `clips_comments` flags                 | false / unapplied on prod |

**Do not activate** these in audit sessions without explicit founder approval.

---

## External dependencies

| ID          | Dependency                                | Blocks                               |
| ----------- | ----------------------------------------- | ------------------------------------ |
| **EXT-001** | Lenco sandbox credentials (F9b)           | RG-4 money drill                     |
| **EXT-002** | Zamtel collections decision (FD-01)       | Checkout rail honesty                |
| **EXT-003** | Meta WhatsApp Cloud production setup (F5) | Transactional notifications at scale |

---

_Re-evaluate after Batch 1 live verification._
