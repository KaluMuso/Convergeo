import { describe, expect, it } from "vitest";

import {
  defaultEndsAtForStart,
  draftToPayload,
  endsAtAfterStartChange,
  toInstanceDraft,
  validateInstanceDrafts,
  type InstanceDraft,
} from "./instance-editor";

const BASE_DRAFT: InstanceDraft = {
  key: "instance-1",
  startsAt: "2026-09-12T18:00",
  endsAt: "2026-09-12T20:00",
  capacity: "50",
};

describe("event instance times", () => {
  it("defaults an end to two hours after its start", () => {
    expect(defaultEndsAtForStart("2026-09-12T23:00")).toBe("2026-09-13T01:00");
    expect(
      toInstanceDraft({
        id: "instance-1",
        starts_at: "2026-09-12T18:00:00+02:00",
        ends_at: null,
        capacity: 50,
      }).endsAt,
    ).toBe("2026-09-12T20:00");
  });

  it("moves an automatically derived end when the start changes", () => {
    expect(endsAtAfterStartChange("2026-09-12T18:00", "2026-09-12T20:00", "2026-09-12T19:30")).toBe(
      "2026-09-12T21:30",
    );
  });

  it("preserves a custom end that remains after the new start", () => {
    expect(endsAtAfterStartChange("2026-09-12T18:00", "2026-09-13T01:00", "2026-09-12T19:30")).toBe(
      "2026-09-13T01:00",
    );
  });

  it("requires an end strictly after its start", () => {
    expect(validateInstanceDrafts([BASE_DRAFT])).toBeNull();
    expect(validateInstanceDrafts([{ ...BASE_DRAFT, endsAt: BASE_DRAFT.startsAt }])).toBe(
      "ends_before_starts",
    );
    expect(validateInstanceDrafts([{ ...BASE_DRAFT, endsAt: "" }])).toBe("required");
  });

  it("always serializes an explicit end timestamp", () => {
    expect(draftToPayload([BASE_DRAFT])).toEqual([
      {
        starts_at: new Date(BASE_DRAFT.startsAt).toISOString(),
        ends_at: new Date(BASE_DRAFT.endsAt).toISOString(),
        capacity: 50,
      },
    ]);
  });
});
