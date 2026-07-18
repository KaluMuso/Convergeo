import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { classifyAdminRequestError } from "./admin-request";

describe("classifyAdminRequestError", () => {
  it("maps 401/403 and forbidden code to permission-denied", () => {
    expect(classifyAdminRequestError(new ApiError("forbidden", "no", { status: 403 })).kind).toBe(
      "permission",
    );
    expect(
      classifyAdminRequestError(new ApiError("unauthorized", "no", { status: 401 })).kind,
    ).toBe("permission");
    expect(classifyAdminRequestError(new ApiError("forbidden", "no", { status: 400 })).kind).toBe(
      "permission",
    );
  });

  it("maps other ApiErrors and unknowns to generic", () => {
    expect(classifyAdminRequestError(new ApiError("boom", "no", { status: 500 })).kind).toBe(
      "generic",
    );
    expect(classifyAdminRequestError(new Error("network")).kind).toBe("generic");
    expect(classifyAdminRequestError("nope").kind).toBe("generic");
  });
});
