# Clip moderation policy (M17-P07)

**Status:** active from the moment the `clips` feature flag is switched on.
**Owner:** founder / admin reviewer.
**Scope:** every video clip on Vergeo5. Nothing else.

This document is the written rule the code implements. Where the two disagree,
the code is the bug.

---

## 1. Nothing publishes without a human

A clip's only path to `published` is `POST /admin/clips/{id}/approve`, called by
an authenticated admin. There is no auto-approval, no "approve if the model is
confident", and no bulk-approve endpoint — approval is one person's decision
about one clip, and the absence of a batch endpoint keeps that structural rather
than a matter of reviewer discipline.

The automated screen (M17-P02) can only **reject**. Passing it moves a clip to
`pending_review`, which is a queue position, not a decision.

## 2. What approval does and does not judge

The reviewer judges **content**. The machine still owns **validity**: approval is
refused, with a 422 and a list of problems, when

- either the 480p or the 720p rendition is missing,
- the WebP poster is missing, or
- the duration is absent or exceeds the 60-second cap (D-V3).

A malformed clip cannot be published by an admin's click. This is not a warning
that can be clicked through.

## 3. Rejection

`POST /admin/clips/{id}/reject` **requires a reason**. The reason is stored on
the clip and shown to the vendor in their studio. A rejection a vendor cannot act
on is indistinguishable from their clip disappearing, and a vendor who cannot
tell those apart stops posting.

`rejected` is terminal. A vendor who fixes the problem uploads a new clip; there
is no resubmit edge, because a resubmit that skips the screen would be a hole and
a resubmit that repeats it is just a new upload.

## 4. Takedown

`POST /admin/clips/{id}/takedown` moves a `published` clip to `taken_down`.

**It is instant.** `taken_down` is outside the public RLS predicate, so the very
next read of the feed cannot return the clip. There is no cache to purge and no
propagation delay to wait out. The tests assert this by _asking the feed_, not by
trusting the timing.

Takedown requires a reason, for the same purpose as rejection.

## 5. Reports and the 24-hour triage target

Shoppers report clips through `POST /clips/{id}/report`, deduplicated by
`(clip_id, reporter_id)` so one person cannot inflate a queue.

**Target: every report is triaged within 24 hours (S3).** The admin queue shows
each report's age and flags anything past the target. The target is visible in
the tool rather than living in a document nobody opens.

Two outcomes, both final and both audited:

| Outcome     | Effect on the clip     | Effect on the vendor |
| ----------- | ---------------------- | -------------------- |
| **Dismiss** | none                   | none                 |
| **Uphold**  | taken down immediately | counts as one strike |

There is deliberately no "snooze". A report sitting unresolved is the failure the
target exists to prevent.

## 6. The strike rule

> **Three upheld takedowns within 90 days suspends the vendor.**

- The window is trailing, counted from `taken_down_at`.
- Both routes to a takedown count: an admin-initiated takedown and an upheld
  report are the same strike.
- A rejection is **not** a strike. A rejected clip was never public, so nobody
  was harmed by it; treating rejections as strikes would punish vendors for using
  the review process as intended.
- Suspension reuses the existing `admin_flags` cascade
  (`transition_vendor_suspend`), so a suspended vendor is suspended everywhere —
  there is not a second, clip-specific notion of suspension that could disagree
  with the first.
- **Suspension hides all of that vendor's published clips**, each through the
  guarded transition so each takedown is individually audited.

Suspension is reversible by an admin through the existing vendor controls; this
document does not create a separate un-suspend path.

## 7. Audit and idempotency

- Every action writes an `audit_log` row through `AdminAuditRecorder` with a
  before/after snapshot and the acting admin.
- Every action is **idempotent**: replaying it produces the same end state, one
  effect and one audit row. Approving an already-published clip is a no-op that
  returns 200, not an error.
- Every action is **concurrency-safe**: the from-state is asserted inside the
  UPDATE, so two simultaneous reviewers produce exactly one transition and the
  loser is told (409 `clip_transition_conflict`) rather than silently overwriting.

## 8. Previewing non-public clips

A clip awaiting review has no public delivery URL. The reviewer sees it through
**short-lived preview links (≤5 minutes)** returned by
`GET /admin/clips/{id}` — the same posture as the `kyc-docs` bucket. A leaked
review link stops working before it can be passed around.

## 9. What this policy does not cover

- Comments (`clips_comments`, F-V2, shipped off) — when enabled, comments are
  keyword-screened before persistence and reportable through the same queue.
- Cancel-rate governance, which is `vendor_governance.py`'s separate signal and
  a different failure mode entirely.
- Any automated enforcement. Every action in this document is taken by a person.
