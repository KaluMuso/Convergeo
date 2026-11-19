import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { decisionErrorKey, mapsUrl, safeEvidenceUrl } from "./api";

describe("branch admin helpers", () => {
  it("maps known decision refusals", () => {
    const open = new ApiError("conflict", "x", {
      status: 409,
      details: { message_key: "admin.branches.errors.openFlags" },
    });
    expect(decisionErrorKey(open)).toBe("branches.errors.openFlags");
    const vendorSide = new ApiError("conflict", "x", {
      status: 409,
      details: { message_key: "vendor.branches.errors.evidenceRequired" },
    });
    expect(decisionErrorKey(vendorSide)).toBe("branches.errors.invalidTransition");
    expect(decisionErrorKey(new ApiError("forbidden", "x", { status: 403 }))).toBe(
      "branches.errors.permission",
    );
    expect(decisionErrorKey(new Error("x"))).toBe("branches.errors.saveFailed");
  });

  it("only renders https evidence links", () => {
    expect(safeEvidenceUrl("https://x.supabase.co/storage/v1/object/sign/a.jpg?token=1")).toMatch(
      /^https:/,
    );
    expect(safeEvidenceUrl("javascript:alert(1)")).toBeNull();
    expect(safeEvidenceUrl("http://insecure/a.jpg")).toBeNull();
    expect(safeEvidenceUrl(null)).toBeNull();
  });

  it("builds a maps link", () => {
    expect(mapsUrl(-15.4167, 28.2833)).toBe("https://www.google.com/maps?q=-15.416700,28.283300");
  });
});
