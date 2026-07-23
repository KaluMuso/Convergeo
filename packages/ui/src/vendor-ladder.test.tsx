import { describe, expect, it } from "vitest";

import {
  COMMERCIAL_TIER_ORDER,
  normalizeCommercialTier,
  resolveTrustLevel,
  trustLevelForCard,
} from "./vendor-ladder";

describe("vendor-ladder", () => {
  it("keeps commercial tier order bronze → platinum", () => {
    expect(COMMERCIAL_TIER_ORDER).toEqual(["bronze", "silver", "gold", "platinum"]);
  });

  it("maps trust ladder separately from commercial tier", () => {
    expect(resolveTrustLevel({ preferredBadge: true, kycTier: 3 })).toBe("preferred");
    expect(resolveTrustLevel({ preferredBadge: false, kycTier: 2 })).toBe("sector_verified");
    expect(resolveTrustLevel({ preferredBadge: false, kycTier: 1 })).toBe("id_verified");
    expect(resolveTrustLevel({ preferredBadge: false, kycTier: null })).toBe("self_listed");
  });

  it("hides self-listed on compact cards", () => {
    expect(trustLevelForCard({ preferredBadge: false, kycTier: null })).toBeUndefined();
    expect(trustLevelForCard({ preferredBadge: false, kycTier: 1 })).toBe("id_verified");
  });

  it("normalizes null commercial tier to bronze", () => {
    expect(normalizeCommercialTier(null)).toBe("bronze");
    expect(normalizeCommercialTier(undefined)).toBe("bronze");
    expect(normalizeCommercialTier("gold")).toBe("gold");
    expect(normalizeCommercialTier("invalid")).toBe("bronze");
  });
});
