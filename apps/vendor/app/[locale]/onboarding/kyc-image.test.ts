import { describe, expect, it } from "vitest";

import {
  ACCEPTED_KYC_IMAGE_TYPES,
  MAX_KYC_DOC_BYTES,
  validateKycImageFile,
} from "./_lib/kyc-image";

describe("validateKycImageFile", () => {
  it("accepts common raster types within the size limit", () => {
    for (const type of ACCEPTED_KYC_IMAGE_TYPES) {
      expect(validateKycImageFile({ type, size: 1024 })).toBeNull();
    }
  });

  it("rejects empty or unknown types", () => {
    expect(validateKycImageFile({ type: "application/pdf", size: 100 })).toBe("invalid_type");
    expect(validateKycImageFile({ type: "image/jpeg", size: 0 })).toBe("invalid_type");
  });

  it("rejects files above the signed-upload cap", () => {
    expect(validateKycImageFile({ type: "image/jpeg", size: MAX_KYC_DOC_BYTES + 1 })).toBe(
      "too_large",
    );
  });
});
