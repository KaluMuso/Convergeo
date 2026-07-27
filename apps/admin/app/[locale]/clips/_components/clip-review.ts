/**
 * M17-P07 — the review decisions expressed as pure functions.
 *
 * Extracted from the panel so they can be tested without a DOM, and so the two
 * rules that matter live in one readable place rather than inside a JSX
 * `disabled=` expression:
 *
 * * approve is offered only for a `pending_review` clip whose media is ready —
 *   the API refuses anything else, and a button that reliably 422s teaches
 *   reviewers to click through errors;
 * * reject and takedown are offered only with a reason, because a decision a
 *   vendor cannot act on is indistinguishable from their clip vanishing.
 */

export const PENDING_REVIEW = "pending_review";
export const PUBLISHED = "published";

export type ReviewSubject = {
  status: string;
  media_ready: boolean;
};

export function canApprove(clip: ReviewSubject): boolean {
  return clip.status === PENDING_REVIEW && clip.media_ready;
}

export function canReject(clip: ReviewSubject, reason: string): boolean {
  return reason.trim().length > 0 && clip.status !== "rejected";
}

export function canTakeDown(clip: ReviewSubject, reason: string): boolean {
  return clip.status === PUBLISHED && reason.trim().length > 0;
}

/** Map an API error code onto the message key the reviewer should see. */
export function decisionErrorKey(code: string | undefined): string {
  switch (code) {
    case "clip_transition_conflict":
    case "clip_invalid_transition":
      return "conflict";
    case "clip_media_not_ready":
      return "mediaNotReady";
    default:
      return "failed";
  }
}
