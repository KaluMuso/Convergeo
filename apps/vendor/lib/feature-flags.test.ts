import { describe, expect, it } from "vitest";

import { parseStringAllowlist } from "./feature-flags";

describe("parseStringAllowlist", () => {
  it("parses json arrays", () => {
    expect(parseStringAllowlist(["vendor-a", "vendor-b"])).toEqual(["vendor-a", "vendor-b"]);
  });

  it("parses json-encoded strings", () => {
    expect(parseStringAllowlist('["vendor-a"]')).toEqual(["vendor-a"]);
  });

  it("returns empty for invalid values", () => {
    expect(parseStringAllowlist(null)).toEqual([]);
    expect(parseStringAllowlist("not-json")).toEqual([]);
    expect(parseStringAllowlist({})).toEqual([]);
  });
});
