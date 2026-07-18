import { describe, expect, it } from "vitest";

import {
  canUseWholesaleCapabilities,
  effectiveKycTier,
  hasAuditableKycRecord,
  isAuditableApproved,
  shouldShowPreferredBadge,
} from "./kyc-integrity";

describe("kyc integrity (VEND-01)", () => {
  it("rejects approved status without an auditable record id", () => {
    const orphaned = {
      kyc_tier: 2,
      kyc_status: "approved",
      kyc_record_id: null,
      kyc_record_status: null,
    };
    expect(hasAuditableKycRecord(orphaned)).toBe(false);
    expect(isAuditableApproved(orphaned)).toBe(false);
    expect(effectiveKycTier(orphaned)).toBeNull();
    expect(canUseWholesaleCapabilities(orphaned)).toBe(false);
  });

  it("allows wholesale only for auditable approved tier ≥ 2", () => {
    const t2 = {
      kyc_tier: 2,
      kyc_status: "approved",
      kyc_record_id: "rec-1",
      kyc_record_status: "approved",
    };
    expect(isAuditableApproved(t2)).toBe(true);
    expect(effectiveKycTier(t2)).toBe(2);
    expect(canUseWholesaleCapabilities(t2)).toBe(true);
  });

  it("keeps T1 approved shops without wholesale", () => {
    const t1 = {
      kyc_tier: 1,
      kyc_status: "approved",
      kyc_record_id: "rec-2",
      kyc_record_status: "approved",
    };
    expect(canUseWholesaleCapabilities(t1)).toBe(false);
    expect(effectiveKycTier(t1)).toBe(1);
  });

  it("never invents preferred badge from tier", () => {
    expect(shouldShowPreferredBadge(undefined)).toBe(false);
    expect(shouldShowPreferredBadge(false)).toBe(false);
    expect(shouldShowPreferredBadge(true)).toBe(true);
  });
});
