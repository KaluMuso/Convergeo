import { ApiError } from "@vergeo/config";
import { describe, expect, it } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";
import { canUseWholesaleCapabilities } from "../../_lib/kyc-integrity";

import { applyListingFieldPatch, DEFAULT_LISTING_FIELDS } from "./_components/listing-fields";
import { listingCreateErrorMessage } from "./_lib/listing-errors";
import { isValidUnitDecimal, unitDecimalToMilli } from "./_lib/measure";
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
    expect(vendorMessages.listings.fields.classA).toBe("A. Branded SKU");
    expect(vendorMessages.listings.fields.classB).toBe("B. Branded variant");
    expect(vendorMessages.listings.fields.classC).toBe("C. Commodity / generic");
    expect(vendorMessages.listings.fields.conditionDetailLabel).toBe("Condition detail");
    expect(vendorMessages.listings.fields.pricingQuoteOnly).toBe("Quote only");
    expect(vendorMessages.listings.errors.standalone_required).toBeTruthy();
  });
});

describe("listing unit-step conversion", () => {
  it("converts three-decimal increments to integer milli-units", () => {
    expect(unitDecimalToMilli("0.125")).toBe(125);
    expect(unitDecimalToMilli("2.5")).toBe(2_500);
  });

  it("returns a validation error for unsafe or over-precise increments", () => {
    expect(isValidUnitDecimal("9007199254740992")).toBe(false);
    expect(isValidUnitDecimal("0.0001")).toBe(false);
  });
});

describe("product-class form rules", () => {
  it("forces Class D to used condition with a used-tier detail", () => {
    const fields = applyListingFieldPatch(DEFAULT_LISTING_FIELDS, { productClass: "D" });
    expect(fields.condition).toBe("used");
    expect(fields.conditionDetail).toBe("used_good");
  });

  it("forces Class E to made-to-order fulfilment", () => {
    const fields = applyListingFieldPatch(DEFAULT_LISTING_FIELDS, { productClass: "E" });
    expect(fields.fulfilmentMode).toBe("made_to_order");
    expect(fields.stockMode).toBe("always_available");
  });
});

describe("listing create errors", () => {
  it("maps the standalone-class API error to vendor-facing copy", () => {
    const message = listingCreateErrorMessage(
      new ApiError("standalone_product_class_required", "Use quick list", { status: 422 }),
      {
        standaloneRequired: vendorMessages.listings.errors.standalone_required,
        fallback: vendorMessages.listings.errors.submitFailed,
      },
    );

    expect(message).toBe(vendorMessages.listings.errors.standalone_required);
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
