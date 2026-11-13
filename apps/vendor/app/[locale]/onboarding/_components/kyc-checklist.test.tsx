// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { KycChecklistCard } from "./kyc-checklist";

import type { KycApplication } from "../_lib/types";

afterEach(() => {
  cleanup();
});

const app: KycApplication = {
  vendor_id: "v1",
  vendor_status: "pending_kyc",
  kyc_tier: null,
  kyc_status: "rejected",
  tier: null,
  kyc_record_id: null,
  kyc_record_status: null,
  business_name: "Chanda Electronics",
  business_category: "electronics",
  business_archetype: "market_trader",
  momo_phone: "0977123456",
  nrc_path: "kyc/nrc.jpg",
  selfie_path: "kyc/selfie.jpg",
  rejection_reason: "NRC photo is blurry",
  rejected_docs: ["nrc"],
  updated_at: "2026-11-12T00:00:00Z",
};

describe("KycChecklistCard", () => {
  it("shows each step's status, the reviewer's reason and how to fix it", () => {
    render(
      <NextIntlClientProvider locale="en" messages={{ vendor: vendorMessages }}>
        <KycChecklistCard application={app} locale="en" />
      </NextIntlClientProvider>,
    );
    const card = screen.getByTestId("vendor-kyc-checklist");
    expect(card).toHaveAttribute("data-overall", "needs_fix");
    const nrc = card.querySelector('[data-item="nrc"]') as HTMLElement;
    expect(nrc).toHaveAttribute("data-state", "rejected");
    expect(nrc).toHaveAttribute("aria-current", "step");
    expect(within(nrc).getByText("Needs a fix")).toBeInTheDocument();
    expect(within(nrc).getByText(/retake the NRC photo in daylight/)).toBeInTheDocument();
    expect(screen.getByText("NRC photo is blurry")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fix and send again" })).toHaveAttribute(
      "href",
      "/en/onboarding",
    );
  });
});
