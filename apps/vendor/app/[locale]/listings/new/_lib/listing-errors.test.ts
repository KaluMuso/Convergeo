import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import { describeListingError } from "./listing-errors";

const messages = {
  standaloneRequired: "standalone",
  policyBlocked: "policy",
  draftInvalid: "Draft not saved: fix the highlighted fields.",
  publishBlocked: "Cannot publish yet: category or release rules.",
  fieldErrors: { required: "This field is required" },
  fallback: "fallback",
};

function fieldError(code: string, fields: unknown) {
  return new ApiError(code, "Validation failed", { status: 422, details: { fields } });
}

describe("describeListingError", () => {
  it("places server field errors next to their fields and uses draft wording", () => {
    const result = describeListingError(
      fieldError("listing_draft_invalid", [
        { field: "defect_notes", code: "required", message: "raw" },
        { field: "price_ngwee", code: "other", message: "Price too low" },
      ]),
      messages,
      "draft",
    );
    expect(result.message).toBe(messages.draftInvalid);
    expect(result.fields).toEqual({
      defect_notes: "This field is required",
      price_ngwee: "Price too low",
    });
    expect(result.unplaced).toEqual([]);
  });

  it("uses different wording for a blocked publish", () => {
    const result = describeListingError(
      fieldError("listing_publish_blocked", [
        { field: "product_class", code: "release_policy", message: "Class not released" },
      ]),
      messages,
      "publish",
    );
    expect(result.message).toBe(messages.publishBlocked);
    expect(result.message).not.toBe(messages.draftInvalid);
    expect(result.fields.product_class).toBe("Class not released");
  });

  it("reports form-level issues in the summary instead of a field", () => {
    const result = describeListingError(
      fieldError("listing_publish_blocked", [
        { field: "vendor", code: "kyc", message: "Verify your ID" },
      ]),
      messages,
      "publish",
    );
    expect(result.fields).toEqual({});
    expect(result.unplaced).toEqual(["Verify your ID"]);
  });

  it("falls back for non-API errors", () => {
    const result = describeListingError(new Error("boom"), messages);
    expect(result.message).toBe("fallback");
    expect(result.fields).toEqual({});
  });
});
