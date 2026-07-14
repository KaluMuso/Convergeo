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
| **D1** | Event instances have no end time → escrow releases mid-event, discovery drops events at start, `.ics` assumes 2h | **Fixed** (§3) |
| **D2** | Category + landmark stored inside an HTML comment in `events.description`; browse/detail hardcode `category=None`, so non-free category filters return nothing | **Fixed** (§4) |
| **D3** | Organiser cancellation only flags an admin audit row — no automatic refund or buyer notification | **Fixed — approach (b)** (§5) |

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

## 4. D2 — Category normalisation (DONE)

Category + landmark were serialised into `<!--vergeo5:event-meta:{…}-->` appended to
`events.description` and parsed at runtime. Beyond fragility this was a live bug:
`events_public` browse/detail hardcoded `category=None` and never read the meta, so
filtering by any of the 5 non-free categories returned nothing.

**Shipped:**

- `0035_event_categories.sql` — `event_categories` taxonomy table (`slug`, `parent_slug`,
  `label_key`, `sort`), seeded with the 6 launch categories (`parent_slug` ready for the
  strategy's ~11 top-level / ~65 subcategory nesting); `events.category_slug` FK + index;
  `events.landmark` column; backfill from the meta comment + strip it from the description.
  Additive + reversible.
- organiser create/edit write `category_slug` + `landmark` columns and a clean description;
  reads come from the columns. The HTML-comment reader/writer is fully removed.
- `events_public` browse filters on the real `category_slug` (fixes the filter bug); detail
  surfaces the event-specific landmark (fallback to the organiser's vendor-location
  landmark).
- Tests: category-slug filtering, detail category/landmark, organiser category/landmark edit.

**Follow-up (not blocking):** event search documents still index a generic `category_path`
of `events` rather than the specific category — a search-ranking refinement, separate from
the acute browse-filter bug fixed here.

## 5. D3 — Cancellation → refund queue + notification (DONE — approach (b))

Cancel previously only set `status='cancelled'`; refunds were flagged lazily by the escrow
sweep and buyers were never notified.

**Shipped (approach (b) — money stays behind a human gate):** `app/services/events/
cancellation.py::process_event_cancellation`, invoked from the cancel endpoint after the
status transition (best-effort; the escrow sweep re-flags on failure):

- flags each **paid** ticket order for admin mass-refund immediately, reusing the escrow
  sweep's `MASS_REFUND_FLAG_ACTION` audit signal (idempotent + cross-deduped with the sweep);
- notifies every affected **buyer and current ticket holder** via the outbox
  (`event_cancelled`);
- **does not move money** — an admin still executes each refund payout via the untouched
  `services.refunds.execute_refund`.

Note: pre-creating `refunds` rows was rejected on purpose — `execute_refund` short-circuits
on any active (`pending`/`processing`/`completed`) refund and the unique-active-refund index
forbids duplicates, so a pre-created `pending` row would *block* execution rather than queue
it. The refund row is therefore still born at admin execution time.

Tests: paid-order flag + buyer/holder notification, idempotency, unpaid-order skip, and the
end-to-end cancel endpoint wiring.

**Upgrade path to (a):** when desired, call `execute_refund` per flagged order automatically
(full auto-refund) instead of leaving it to the admin — no schema change needed.

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
