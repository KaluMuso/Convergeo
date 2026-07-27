import { describe, expect, it } from "vitest";

import { canApprove, canReject, canTakeDown, decisionErrorKey } from "./clip-review";

/**
 * M17-P07 — the review gates, tested where they live.
 *
 * These are the rules the reviewer meets as enabled/disabled buttons; the
 * server-side proof that they are actually enforced is in
 * `services/api/tests/test_admin_clips.py`. Both exist because the UI rule is
 * about not teaching reviewers to click through errors, and the API rule is
 * about what happens when someone bypasses the UI entirely.
 */

describe("canApprove", () => {
  it("allows approving a pending_review clip whose media is ready", () => {
    expect(canApprove({ status: "pending_review", media_ready: true })).toBe(true);
  });

  it("refuses a clip whose media is not ready", () => {
    // The API refuses this with a 422; offering the button anyway would teach
    // reviewers that errors are normal.
    expect(canApprove({ status: "pending_review", media_ready: false })).toBe(false);
  });

  it("refuses any status other than pending_review", () => {
    for (const status of ["draft", "screening", "published", "rejected", "taken_down"]) {
      expect(canApprove({ status, media_ready: true })).toBe(false);
    }
  });
});

describe("canReject", () => {
  it("requires a reason", () => {
    const clip = { status: "pending_review", media_ready: true };
    expect(canReject(clip, "")).toBe(false);
    expect(canReject(clip, "   ")).toBe(false);
    expect(canReject(clip, "blurry")).toBe(true);
  });

  it("does not offer rejecting an already-rejected clip", () => {
    expect(canReject({ status: "rejected", media_ready: true }, "blurry")).toBe(false);
  });
});

describe("canTakeDown", () => {
  it("applies only to a published clip, and only with a reason", () => {
    expect(canTakeDown({ status: "published", media_ready: true }, "unsafe")).toBe(true);
    expect(canTakeDown({ status: "published", media_ready: true }, " ")).toBe(false);
    expect(canTakeDown({ status: "pending_review", media_ready: true }, "unsafe")).toBe(false);
  });
});

describe("decisionErrorKey", () => {
  it("distinguishes a concurrent decision from a generic failure", () => {
    expect(decisionErrorKey("clip_transition_conflict")).toBe("conflict");
    expect(decisionErrorKey("clip_invalid_transition")).toBe("conflict");
  });

  it("names the media problem explicitly", () => {
    expect(decisionErrorKey("clip_media_not_ready")).toBe("mediaNotReady");
  });

  it("falls back to a generic failure for anything unrecognised", () => {
    expect(decisionErrorKey(undefined)).toBe("failed");
    expect(decisionErrorKey("something_new")).toBe("failed");
  });
});
