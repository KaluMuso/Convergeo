import { describe, expect, it } from "vitest";

import { groupByInstance } from "./group-roster";

import type { RosterAttendee } from "./roster-client";

function attendee(overrides: Partial<RosterAttendee> = {}): RosterAttendee {
  return {
    ticket_id: "t1",
    holder_name: "Chanda",
    ticket_type_id: "tt1",
    ticket_type_name: "GA",
    kind: "fixed",
    instance_id: "i1",
    starts_at: "2026-08-01T18:00:00+00:00",
    status: "issued",
    checked_in_at: null,
    ...overrides,
  };
}

describe("groupByInstance", () => {
  it("returns an empty list for no attendees", () => {
    expect(groupByInstance([])).toEqual([]);
  });

  it("groups rows sharing an instance and keeps first-seen order", () => {
    const rows = [
      attendee({ ticket_id: "a", instance_id: "i1", starts_at: "2026-08-01T18:00:00+00:00" }),
      attendee({ ticket_id: "b", instance_id: "i2", starts_at: "2026-08-02T18:00:00+00:00" }),
      attendee({ ticket_id: "c", instance_id: "i1", starts_at: "2026-08-01T18:00:00+00:00" }),
    ];
    const groups = groupByInstance(rows);
    expect(groups.map((g) => g.instanceId)).toEqual(["i1", "i2"]);
    expect(groups.map((g) => g.attendees.map((a) => a.ticket_id))).toEqual([["a", "c"], ["b"]]);
  });

  it("takes startsAt from the first row of each group", () => {
    const groups = groupByInstance([
      attendee({ instance_id: "i9", starts_at: "2026-09-09T09:00:00+00:00" }),
    ]);
    expect(groups.map((g) => g.startsAt)).toEqual(["2026-09-09T09:00:00+00:00"]);
  });
});
