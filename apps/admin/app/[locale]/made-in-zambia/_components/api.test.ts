import { describe, expect, it } from "vitest";

import { decisionBody, decisionsFor } from "./api";

describe("made in zambia claim helpers", () => {
  it("mirrors the api state machine", () => {
    expect(decisionsFor("claimed")).toEqual(["approve", "reject"]);
    expect(decisionsFor("approved")).toEqual(["reject"]); // revoke only
    expect(decisionsFor("rejected")).toEqual([]);
  });

  it("sends the note only when it has content", () => {
    expect(decisionBody("approve", "  ")).toEqual({ decision: "approve" });
    expect(decisionBody("reject", " Expired certificate ")).toEqual({
      decision: "reject",
      note: "Expired certificate",
    });
  });
});
