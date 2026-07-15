# Events Strategy — Remediation Plan & Status

**Branch:** `claude/convergeo-strategy-gaps-06qyby`
**Source report:** the Codex "Events Strategy" audit (traceability matrix + branch inventory)
**Baseline at start:** `master` with migrations through `0034`. This work added `0035`,
`0036`, and `0039` (the search-index migration was renumbered from `0037` upstream after a
parallel `0037_vendor_archetype` landed — see the PR ledger in §8).

## 1. Read this first: what the Codex report is (and isn't)

The report was requested as a _vulnerability_ review but is actually a **product-strategy
compliance audit** against `Convergeo_Events_Strategy.pdf`. That distinction drives
prioritisation. Of its 122 assessed items:

- **~4 are genuine defects** — real correctness/trust bugs worth fixing regardless of
  strategy. Only one (escrow timing) touches money. **All are now fixed and merged** (§2–§5).
- **~60 are unbuilt roadmap features** (promo codes, affiliate links, city guides,
  pay-what-you-want, near-me ranking, attendee messaging, team roles, …). Many are
  **explicitly Phase 2/3** in the strategy itself. _An unscheduled, unbuilt feature is
  not a vulnerability or a bug._ These are a product-scope menu (§6), not a fix list — they
  belong in the GATED planning process and need founder direction before any build starts.
- The remainder are "Partial", "Later phase", or "Operational evidence" (needs live data).

The Codex traceability matrix remains the row-by-row reference. This document is the
**action plan**: it isolates the genuine defects, records what shipped, and sequences the rest.

## 2. Genuine defects — all fixed

| ID     | Defect                                                                                                                                                         | Status                        | PR(s)      |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- | ---------- |
| **D1** | Event instances have no end time → escrow releases mid-event, discovery drops events at start, `.ics` assumes 2h                                               | **Fixed** (§3)                | #190, #194 |
| **D2** | Category + landmark stored inside an HTML comment in `events.description`; browse/detail hardcode `category=None`, so non-free category filters return nothing | **Fixed** (§4)                | #190, #197 |
| **D3** | Organiser cancellation only flags an admin audit row — no automatic refund or buyer notification                                                               | **Fixed — approach (b)** (§5) | #190       |

A fourth, smaller trust-signal gap — the **verified-organiser badge** was computed but never
surfaced on event cards (audit rows O-05 / D-12) — was completed alongside the defect work
(§5.1, #201).

## 3. D1 — Event end time (DONE — merged)

Root cause: `event_instances` carried only `starts_at`, so every consumer fabricated an
end from a fixed 2h assumption.

**Backend (non-breaking) — #190:**

- `0035_event_instance_ends_at.sql` — nullable `ends_at` + `CHECK (ends_at IS NULL OR
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
- **Discovery** (`events_public.py`): an event stays listed until it _ends_, not when it
  starts. `ends_at` surfaced on the public instance response.
- **`.ics`** (`event_ics.py`): `DTEND` uses the real end time.
- **Organiser API** (`organiser_events.py`): create/edit accept an optional `ends_at`,
  validated `> starts_at` (422 `vendor.events.errors.ends_before_starts`) and mirrored by
  the DB CHECK; editing an end time triggers the schedule-change notification.
- `packages/types/src/db.ts` regenerated to include `event_instances.ends_at`.

**Frontend (DONE — #194):** the follow-up that was deferred in the first pass has shipped.

- Vendor create/edit **end-time input** — `instance-editor.tsx` (datetime-local end field,
  round-trips `ends_at`), `events-client.ts` (`ends_at` on `EventInstance` /
  `EventInstanceInput`), `event-form.tsx` (`ends_before_starts` error surfaced), plus the
  `vendor.events.errors.ends_before_starts` i18n key. Organisers can now set a real end time.
- **JSON-LD `endDate`** (`event-jsonld.tsx`) uses the effective instance end, and
  `isEventIndexable` measures the noindex grace window from the real end, not `start + 2h`.
- Detail page (`e/[slug]/page.tsx`) threads `ends_at` into the JSON-LD input.

**Tests:** escrow end-anchoring (3 DB-free unit tests proving the anchor moved start→end,
incl. legacy-null unchanged); `.ics` honours a real multi-day `ends_at`; discovery keeps an
in-progress event and drops a just-ended one; organiser create accepts `ends_at` and rejects
`ends_at ≤ starts_at`; JSON-LD end-date/indexability unit tests.

**Intentionally not changed (negligible, not a regression):** `sitemap-events.ts` still adds
a 2h constant when deciding staleness — but it feeds a **30-day** exclusion window, so the 2h
term changes nothing observable. The scanner's instance-listing uses an independent
12h-on-`starts_at` grace plus server-provided rotating-QR horizons, not a 2h end assumption.
Neither is worth a migration/round-trip; left as-is by design.

## 4. D2 — Category normalisation (DONE — merged)

Category + landmark were serialised into `<!--vergeo5:event-meta:{…}-->` appended to
`events.description` and parsed at runtime. Beyond fragility this was a live bug:
`events_public` browse/detail hardcoded `category=None` and never read the meta, so
filtering by any of the 5 non-free categories returned nothing.

**Shipped — #190:**

- `0036_event_categories.sql` — `event_categories` taxonomy table (`slug`, `parent_slug`,
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

**Search follow-up (DONE — #197):** `0039_event_search_category_path.sql` rewrites
`search_upsert_event` so the search index stores each event under its real
`events/<category_slug>` path (was a literal `events`), and reindexes published events.
Backward-compatible — the search filter matches on a `category_path` prefix, so old rows kept
working until reindexed. Category-scoped search now ranks and filters correctly.

## 5. D3 — Cancellation → refund queue + notification (DONE — approach (b), merged)

Cancel previously only set `status='cancelled'`; refunds were flagged lazily by the escrow
sweep and buyers were never notified.

**Shipped — #190 (approach (b) — money stays behind a human gate):**
`app/services/events/cancellation.py::process_event_cancellation`, invoked from the cancel
endpoint after the status transition (best-effort; the escrow sweep re-flags on failure):

- flags each **paid** ticket order for admin mass-refund immediately, reusing the escrow
  sweep's `MASS_REFUND_FLAG_ACTION` audit signal (idempotent + cross-deduped with the sweep);
- notifies every affected **buyer and current ticket holder** via the outbox
  (`event_cancelled`);
- **does not move money** — an admin still executes each refund payout via the untouched
  `services.refunds.execute_refund`.

Note: pre-creating `refunds` rows was rejected on purpose — `execute_refund` short-circuits
on any active (`pending`/`processing`/`completed`) refund and the unique-active-refund index
forbids duplicates, so a pre-created `pending` row would _block_ execution rather than queue
it. The refund row is therefore still born at admin execution time.

Tests: paid-order flag + buyer/holder notification, idempotency, unpaid-order skip, and the
end-to-end cancel endpoint wiring.

**Upgrade path to (a):** when desired, call `execute_refund` per flagged order automatically
(full auto-refund) instead of leaving it to the admin — no schema change needed.

### 5.1 Verified-organiser badge (DONE — #201)

The organiser's `preferred_badge` was already computed server-side but never rendered, so a
verified host looked identical to an unverified one in discovery. #201 adds an optional
`verifiedBadge` overlay slot to the shared `packages/ui` `EventCard` and renders a "Verified"
badge on browse cards when `organiser.preferred_badge` is true (`events.browse.verified` i18n
key). Trust signal now visible; no backend change.

## 6. The ~60 roadmap gaps — a prioritised menu (not bugs)

**These are product scope, not defects.** None is started; each needs a founder decision
before a build wave opens. Waves are ordered by dependency (A unblocks the rest) and by
launch value. Pick a wave — or specific items within one — to open the next pebble batch.

**Wave A — schema foundation** _(do first; everything downstream keys off these columns)_
`event_type` (single/multi-day/recurring/free/private), privacy/access codes, recurrence
rules, `holder_name` on tickets, pricing-mode fields (early-bird, group, PWYW bounds, perks),
per-instance ticket-tier allocation, event policy fields.
→ _Decision needed:_ confirm the `event_type` enum + which pricing modes launch first.

**Wave B — lifecycle/trust** _(highest launch-trust value; needs Wave A columns)_
buyer cancellation matrix, reschedule + opt-out window, Tier-1 GMV caps + success
progression, event-specific dispute windows/evidence/SLA, scanner holder/tier response +
audited manual override.
→ _Decision needed:_ the buyer-cancellation refund matrix (who bears fees, cutoff windows).

**Wave C — pricing/discovery/growth** _(revenue + acquisition; largest surface)_
fee absorb/pass-through + buyer fee line, city/neighbourhood/near-me + ranking signals,
promo codes, affiliate attribution, attendee campaigns, richer organiser analytics.
→ _Decision needed:_ fee model (absorb vs pass-through) — this one is contractual, decide early.

**Wave D — operational validation** _(evidence gaps; needs live/staging data, not code)_
organiser onboarding pipeline, multi-device offline scanner drills, staging
refund/cancellation end-to-end, high-volume scan load tests.
→ _Decision needed:_ none — schedule once there's a pilot organiser to run against.

## 7. Verification status

Unlike the original audit environment, this branch has a working `uv`/`pytest` toolchain.
The API suite runs; all non-DB event tests pass. DB-integration and RLS tests **skip**
without a local Postgres (same limitation the Codex audit noted) — the D1 escrow change is
therefore proven via DB-free unit tests that patch the SQL context loader, plus the DB
integration tests remain available to run against a live database. All four PRs below passed
CI (migration replay, typegen drift, RLS matrix, Python API, JS/TS, security, i18n) and merged.

## 8. PR ledger

| PR   | Merge   | Scope                                                                                                     |
| ---- | ------- | --------------------------------------------------------------------------------------------------------- |
| #190 | bc6ac7c | D1–D3 core: `ends_at` + escrow/discovery/ics/timing; category taxonomy; cancellation refund-flag + notify |
| #194 | 8276a21 | D1 frontend: organiser end-time input + end-anchored JSON-LD/indexability                                 |
| #197 | cc8d330 | D2 search: `search_upsert_event` indexes real `events/<category_slug>` path                               |
| #201 | d55a705 | O-05/D-12: verified-organiser badge on event cards                                                        |

Migrations landed: `0035_event_instance_ends_at`, `0036_event_categories`,
`0039_event_search_category_path` (renumbered from `0037` after upstream
`0037_vendor_archetype`).
