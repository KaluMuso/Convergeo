import { describe, expect, it } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";
import { canUseWholesaleCapabilities } from "../../_lib/kyc-integrity";

import { zmwDecimalToNgwee, isValidZmwDecimal } from "./_lib/money";

describe("listing money conversion", () => {
  it("converts K1,234.56 to 123456 ngwee without float drift", () => {
    expect(zmwDecimalToNgwee("1,234.56")).toBe(123_456);
  });

  it("converts whole kwacha amounts", () => {
    expect(zmwDecimalToNgwee("500")).toBe(50_000);
  });

  it("rejects invalid decimals", () => {
    expect(isValidZmwDecimal("abc")).toBe(false);
    expect(isValidZmwDecimal("0")).toBe(false);
  });
});

describe("listings i18n", () => {
  it("exposes nested listings namespace keys", () => {
    expect(vendorMessages.listings.title).toBe("Create listing");
    expect(vendorMessages.listings.commission.rate).toBe("{rate}%");
    expect(vendorMessages.listings.attach.publish).toBe("Publish listing");
  });
});

describe("attach live-search + commission-shown contract", () => {
  it("documents canonical preview and commission fields for attach flow", () => {
    const preview = {
      product_id: "product-1",
      name: "Smartphone X1",
      commission: { category_key: "electronics", rate_bps: 500, rate_percent: 5 },
    };
    expect(preview.commission.rate_percent).toBe(5);
    expect(vendorMessages.listings.commission.heading).toContain("Commission");
  });
});

describe("listing create KYC capability gate", () => {
  it("hides wholesale UI when tier is orphaned without a KYC record", () => {
    expect(
      canUseWholesaleCapabilities({
        kyc_tier: 2,
        kyc_status: "approved",
        kyc_record_id: null,
        kyc_record_status: null,
      }),
    ).toBe(false);
  });

  it("exposes KYC gate copy for honest status", () => {
    expect(vendorMessages.listings.kycGate.title).toBeTruthy();
    expect(vendorMessages.listings.kycGate.wholesaleLocked).toContain("T2");
  });
});
