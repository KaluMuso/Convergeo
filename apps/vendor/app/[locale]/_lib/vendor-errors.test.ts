import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { classifyVendorError, vendorErrorMessageKey } from "./vendor-errors";

describe("vendor error classification", () => {
  it("maps 403 to permission", () => {
    const err = new ApiError("forbidden", "nope", { status: 403 });
    expect(classifyVendorError(err).kind).toBe("permission");
    expect(vendorErrorMessageKey(err, "profile")).toBe("profile.errors.permissionDenied");
  });

  it("maps 401 to auth", () => {
    const err = new ApiError("unauthenticated", "login", { status: 401 });
    expect(classifyVendorError(err).kind).toBe("auth");
    expect(vendorErrorMessageKey(err, "listings")).toBe("listings.errors.authRequired");
  });

  it("maps network failures", () => {
    const err = new ApiError("network_error", "down", { status: 0 });
    expect(classifyVendorError(err).kind).toBe("network");
    expect(vendorErrorMessageKey(err, "home")).toBe("home.errors.loadFailed");
  });
});
