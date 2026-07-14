# Events Strategy — Remediation Plan & Status

**Branch:** `claude/convergeo-strategy-gaps-06qyby`
**Source report:** the Codex "Events Strategy" audit (traceability matrix + branch inventory)
**Baseline:** `master` (migrations through `0033`)

## 1. Read this first: what the Codex report is (and isn't)

The report was requested as a *vulnerability* review but is actually a **product-strategy
compliance audit** against `Convergeo_Events_Strategy.pdf`. That distinction drives
prioritisation. Of its 122 assessed items:

- **~4 are genuine defects** — real correctness/trust bugs worth fixing regardless of
  strategy. Only one (escrow timing) touches money.
- **~60 are unbuilt roadmap features** (promo codes, affiliate links, city guides,
  pay-what-you-want, near-me ranking, attendee messaging, team roles, …). Many are
  **explicitly Phase 2/3** in the strategy itself. *An unscheduled, unbuilt feature is
  not a vulnerability or a bug.*
- The remainder are "Partial", "Later phase", or "Operational evidence" (needs live data).

The Codex traceability matrix remains the row-by-row reference. This document is the
**action plan**: it isolates the genuine defects, records what has been fixed, and
sequences the rest.

## 2. Genuine defects

| ID | Defect | Status |
| --- | --- | --- |
| **D1** | Event instances have no end time → escrow releases mid-event, discovery drops events at start, `.ics` assumes 2h | **Fixed on this branch** (§3) |
| **D2** | Category + landmark stored inside an HTML comment in `events.description`; browse/detail hardcode `category=None`, so non-free category filters return nothing | **Designed, not started** (§4) |
| **D3** | Organiser cancellation only flags an admin audit row — no automatic refund or buyer notification | **Designed, needs a decision** (§5) |

## 3. D1 — Event end time (DONE)

Root cause: `event_instances` carried only `starts_at`, so every consumer fabricated an
end from a fixed 2h assumption.

**Shipped (backend, non-breaking):**

- `0034_event_instance_ends_at.sql` — nullable `ends_at` + `CHECK (ends_at IS NULL OR
  ends_at > starts_at)` + index; existing rows backfilled to `starts_at + 2h`. Additive
  and reversible (down = drop column).
- `app/services/events/timing.py` — single source for the two deliberately different
  fallbacks:
  - `instance_settlement_end` → `ends_at` else **`starts_at`** (escrow: legacy money
    timing unchanged).
  - `instance_display_end` → `ends_at` else **`starts_at + 2h`** (ics/discovery display).
- **Escrow** (`escrow/event_release.py`): full release now `end + 24h` (was `start +
  24h`); phased final release `end + 1d`; the pre-event phase-1 partial stays `start −
  7d`. Instances with no `ends_at` keep their exact prior schedule.
- **Discovery** (`events_public.py`): an event stays listed until it *ends*, not when it
  starts. `ends_at` surfaced on the public instance response.
- **`.ics`** (`event_ics.py`): `DTEND` uses the real end time.
- **Organiser API** (`organiser_events.py`): create/edit accept an optional `ends_at`,
  validated `> starts_at` (422 `vendor.events.errors.ends_before_starts`) and mirrored by
  the DB CHECK; editing an end time triggers the schedule-change notification.

**Tests added:** escrow end-anchoring (3 DB-free unit tests proving the anchor moved from
start→end, incl. legacy-null unchanged); `.ics` honours a real multi-day `ends_at`;
discovery keeps an in-progress event and drops a just-ended one; organiser create accepts
`ends_at` and rejects `ends_at ≤ starts_at`. All existing event tests stay green.

**Deliberately deferred (frontend follow-up — next pebble).** These currently keep the 2h
assumption, which is *not a regression*:

- Vendor create/edit **end-time input** (`instance-editor.tsx`, `events-client.ts`,
  `event-form.tsx`) + the `vendor.events.errors.ends_before_starts` i18n key. Until this
  lands, organisers can't set a custom end from the UI, so new events default to +2h.
- JSON-LD `endDate`, `sitemap-events.ts` staleness, and the scanner offline horizon should
  read `ends_at` (all still assume 2h).
- Regenerate `packages/types/src/db.ts` `event_instances` to include `ends_at`.

## 4. D2 — Category normalisation (designed)

`organiser_events.py` serialises `{category, landmark}` into
`<!--vergeo5:event-meta:{…}-->` appended to the description and parses it back at runtime.
Consequences: category isn't indexed or constrained; **`events_public` browse/detail set
`category=None` and never read the meta, so filtering by any of the 5 non-free categories
returns nothing**; landmark lives outside the geo model; and expanding categories needs
code, not data.

**Plan (additive):**

1. `event_categories` table (`slug`, `parent_slug`, `label_key`, `sort`), seeded with the
   6 launch categories — extensible toward the strategy's ~11 top-level / ~65 subcategories
   without code changes.
2. `events.category_slug` FK (nullable during transition) + index; move landmark onto the
   event/geo model.
3. Backfill `category_slug`/landmark from the parsed meta comment; keep a compatibility
   read during transition; drop the meta writer once backfilled.
4. Wire `events_public` browse/detail (and search projection) to the real column — this
   fixes the category-filter bug.

## 5. D3 — Cancellation → automatic refund + notification (needs a decision)

Today: `organiser_events` cancel sets `status='cancelled'`; the escrow sweep blocks release
and writes an `event_release.mass_refund_flagged` audit row for a human. Strategy promises
automatic 100% refund + buyer notification.

**Plan:** on cancel, enqueue an idempotent refund per paid ticket order via the existing
refund ledger path (`rfd-*`) and emit an `event_cancelled` outbox notification to each
holder.

**Decision required (this moves money):**

- **(a) Full auto-refund on cancel** — strongest trust promise; highest abuse surface.
- **(b) Auto-enqueue + notify immediately, admin executes payout** — keeps a human gate on
  outbound money (recommended default; smallest change to the current escrow model).
- **(c) Threshold split** — auto for small totals, admin gate above a limit.

I'll implement once you pick; (b) is the safest first step and can upgrade to (a) later.

## 6. The ~60 roadmap gaps — sequencing (not bugs)

These are product scope for M10+ pebbles. Suggested waves (map to the audit's E0–E3):

- **Wave A — schema foundation:** `event_type` (single/multi-day/recurring/free/private),
  privacy/access codes, recurrence, `holder_name`, pricing-mode fields (early-bird, group,
  PWYW bounds, perks), per-instance ticket-tier allocation, event policy fields.
- **Wave B — lifecycle/trust:** buyer cancellation matrix, reschedule + opt-out window,
  Tier-1 GMV caps + success progression, event-specific dispute windows/evidence/SLA,
  scanner holder/tier response + audited manual override.
- **Wave C — pricing/discovery/growth:** fee absorb/pass-through + buyer fee line,
  city/neighbourhood/near-me + ranking signals, promo codes, affiliate attribution,
  attendee campaigns, richer organiser analytics.
- **Wave D — operational validation:** organiser pipeline, multi-device offline scanner
  drills, staging refund/cancellation end-to-end, high-volume scan load tests.

## 7. Verification status

Unlike the original audit environment, this branch has a working `uv`/`pytest` toolchain.
The API suite runs; all non-DB event tests pass. DB-integration and RLS tests **skip**
without a local Postgres (same limitation the Codex audit noted) — the D1 escrow change is
therefore proven via DB-free unit tests that patch the SQL context loader, plus the DB
integration tests remain available to run against a live database.
