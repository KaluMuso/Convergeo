import { describe, expect, it } from "vitest";

import { PRIMARY_BRANCH, readActingBranch, serializeActingBranchCookie } from "./acting-branch";

const ID = "aaaaaaaa-0000-0000-0000-0000000000a2";

describe("acting branch cookie", () => {
  it("defaults to the primary shop", () => {
    expect(readActingBranch("")).toBe(PRIMARY_BRANCH);
    expect(readActingBranch("theme=dark")).toBe(PRIMARY_BRANCH);
  });

  it("reads a valid branch id", () => {
    expect(readActingBranch(`theme=dark; cv_branch=${ID.toUpperCase()}`)).toBe(ID);
  });

  it("ignores tampered values", () => {
    expect(readActingBranch("cv_branch=../../admin")).toBe(PRIMARY_BRANCH);
    expect(readActingBranch("cv_branch=%27%3B%20drop")).toBe(PRIMARY_BRANCH);
  });

  it("serializes a scoped, expiring cookie and clears on null", () => {
    expect(serializeActingBranchCookie(ID, true)).toBe(
      `cv_branch=${ID}; Path=/; Max-Age=31536000; SameSite=Lax; Secure`,
    );
    expect(serializeActingBranchCookie(null, false)).toBe(
      "cv_branch=; Path=/; Max-Age=0; SameSite=Lax",
    );
    expect(serializeActingBranchCookie("not-an-id", false)).toContain("Max-Age=0");
  });
});
