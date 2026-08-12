# Events strategy audit — August 2026

Source: `Convergeo_Events_Strategy.pdf`

Audit baseline: current `origin/master` on 9 August 2026, after the event-domain
foundation and later launch-hardening migrations had landed.

## Executive conclusion

The codebase does **not** yet fully implement the strategy document. It now has a
substantial launch foundation, but the document mixes launch requirements,
later-phase roadmap features, and operational proof. Treating all 122 expectations
as "done" would be inaccurate.

This audit separates four different states:

1. implemented and covered by code/tests;
2. implemented foundation with incomplete customer/organiser workflow;
3. unimplemented product scope;
4. operational evidence that cannot be proven from source code alone.

The repository-wide release status remains authoritative in `docs/plan/00-status.md`.
This document does not override its money-path or public-launch gates.

## Launch-critical residuals addressed in this branch

### Non-public event exposure

The final public PostgREST policies required only `status='published'` and an active
organiser. They omitted `events.visibility`, so anonymous callers could enumerate
published `unlisted` and `private` events, their schedules, ticket configuration,
allocations, price tiers, and `access_code_hash`.

Remediation:

- public policies on events and all four public child surfaces now require
  `visibility='public'`;
- unlisted/private detail remains mediated by the service API instead of an
  enumerable base-table policy;
- stale code digests are removed whenever visibility is not private, backed by a
  database constraint and organiser API behavior;
- real-role pgTAP coverage proves anonymous/unrelated-user denial while preserving
  organiser access.

### Cancellation did not terminate ticket validity

The organiser endpoint changed the event status and then ran best-effort refund
flags/notifications. Existing credentials remained `issued`, online check-in did not
check event status, offline scan sync still exported signatures, and the issue worker
could issue tickets after cancellation.

Remediation:

- the event status transition now atomically cancels pending transfers and voids
  active credentials; checked-in rows remain immutable audit evidence;
- new/updated issued credentials require a published parent event, closing the
  issue-versus-cancel race at the database boundary;
- paid-order issuance revalidates successful payment and the status of every event
  before linking or inserting any ticket;
- the pending-issue query excludes orders containing non-published events;
- online/batch verification and offline scan sync fail closed for unavailable events
  (with the database invariant remaining authoritative).

### Paid holds could expire before delayed issuance

The stale-claim sweep treated every old unlinked ticket as unpaid. During an issue
worker outage it could void a successfully paid capacity reservation, after which the
issue path could insert a replacement outside the original claim.

Remediation: stale release now excludes claim IDs belonging to checkout groups with a
successful payment; tests cover a paid but still-unlinked hold through later issuance.

### End times remained optional

Earlier work added `ends_at`, but the column remained nullable for compatibility and
some clients still omitted it.

Remediation:

- a compatibility trigger materializes a two-hour end for legacy inserts;
- start-only reschedules preserve the previous duration;
- `event_instances.ends_at` is now `NOT NULL` and still checked to be after start;
- organiser/customer clients send and consume the explicit end time.

### Cancellation notice overstated refund progress

Cancellation currently creates an admin review flag; it does not create or send a
refund payout. The notice incorrectly said a refund was already being processed.

Remediation: the payload now says the refund is queued for review and that no payout
has been sent. This is intentionally honest until a durable automatic-refund workflow
exists.

## Implemented strategy foundation on current master

The previous remediation plan is historical and understates what has since shipped.
Current foundations include:

- real instance end times and end-anchored discovery, calendar data, and escrow timing;
- relational event category/landmark fields and category-aware search;
- attendee-name capture;
- `event_type`, visibility, access-code hash, refund-policy, age, and terms fields;
- per-instance ticket-type allocation;
- early-bird/group pricing fields;
- Tier-1 GMV cap scaffolding;
- cancellation notifications and manual refund-review flags;
- verified-organiser discovery badges.

These foundations do not by themselves complete the workflows described below.

## Remaining launch blockers and roadmap gaps

### P0 — money safety (separate heightened-scrutiny work)

- **Automatic event-cancellation refunds:** needs a durable per-order job, verified
  refund destination, provider-payout reconciliation, unique payout idempotency,
  resume-after-crash behavior, and an exact mixed released/escrow ledger path. The
  current refund service must not be called in a synchronous cancellation loop.
- **Refund completion semantics:** a refund must not be presented as completed merely
  because a pending payout row was created; provider-paid state must be authoritative.
- **Tier-1 GMV cap atomicity:** the API currently checks successful GMV before checkout.
  Concurrent/pending checkouts can exceed the cap; use transactional GMV reservations.
- **Reschedule settlement snapshot:** settlement branch/due dates currently derive from
  the live schedule. Moving a sold event across the phase boundary can change release
  behavior after purchase; snapshot settlement terms or prohibit that edit temporarily.

### P1 — access and lifecycle workflows

- Private-event unlock must issue a short-lived signed access proof and require it for
  detail, calendar, checkout, and RSVP. This branch fails closed on private purchase
  until that proof exists; plaintext codes must not travel in query strings/logs.
- Buyer cancellation policy, material-reschedule records, a seven-day opt-out/refund
  window, and immutable old/new schedule snapshots remain unimplemented.
- Recurring-event instance generation is deferred; a discriminator alone is not a
  recurrence workflow.
- Scanner manual override with explicit reason/audit remains unimplemented.
- Transfer claim should update attendee display name as well as holder identity/secrets.
- Event-specific dispute windows, evidence, and SLA are incomplete.

### P2 — discovery, pricing, and growth

- Dynamic hierarchical event categories and exact category semantics;
- interactive date/calendar, next-week/month/on-date filters;
- city, neighbourhood, and distance/near-me ranking;
- complete organiser controls and enforcement for event types;
- fee absorb/pass-through presentation and buyer fee line;
- promo codes, affiliates, attendee campaigns, team roles, and richer analytics.

These are product scope, not security patches, and require explicit product decisions.

### Operational evidence (not provable from the repository)

- approved production WhatsApp templates and delivery fallbacks;
- staging cancellation/refund drills on every payment rail;
- multi-device offline scanning and reconciliation drills;
- high-volume scan/load evidence;
- pilot-organiser onboarding and support readiness;
- deployment secrets, workflow activation, dashboards, and alert ownership.

## Safe merge order

1. Merge this access/ticket/end-time hardening after migration replay, pgTAP, API, and
   frontend checks pass.
2. Build the private-event signed access-proof contract.
3. Build the money-path cancellation/refund state machine and atomic GMV reservations
   as dedicated PRs with ledger/failure-path review.
4. Add reschedule opt-out/refund and scanner manual override.
5. Schedule discovery/growth waves only after product decisions are recorded.

## Audit posture

This branch improves genuine defects found against the strategy; it does not certify
full strategy compliance or production readiness. Completion should be claimed only
when the remaining code, money, and operational rows have evidence in their respective
plans and release gates.
