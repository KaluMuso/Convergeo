import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import en from "../../../../../../packages/i18n/messages/en/vendor.json";

import { IntakeReview } from "./intake-review";

import type { IntakeSessionDetail } from "../_lib/intake-client";

const mocks = vi.hoisted(() => ({
  session: { access_token: "test-token" },
  getSession: vi.fn(),
  patchDraft: vi.fn(),
  submit: vi.fn(),
  suggestProducts: vi.fn(),
}));
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: mocks.session, loading: false }),
}));
vi.mock("../_lib/intake-client", () => ({
  createIntakeClient: () => mocks,
}));
vi.mock("../../listings/new/_lib/listing-client", () => ({
  createListingClient: () => ({ suggestProducts: mocks.suggestProducts }),
}));

const productId = "44444444-4444-4444-8444-444444444444";
const detail: IntakeSessionDetail = {
  id: "session-one",
  status: "ready_for_vendor_review",
  draft: {
    title: "Samsung fridge",
    category_id: null,
    price_ngwee: 350000,
    pricing_mode: "fixed",
    quantity: 1,
    stock_mode: "tracked",
    sale_unit: "each",
    condition: "new",
    description: null,
  },
  provenance: [],
  media: [],
  pending_requests: [],
  missing_fields: [],
  submittable: true,
  listing_id: null,
};

function review(sessionId = "session-one") {
  return (
    <NextIntlClientProvider locale="en" timeZone="Africa/Lusaka" messages={{ vendor: en }}>
      <IntakeReview locale="en" sessionId={sessionId} />
    </NextIntlClientProvider>
  );
}

async function chooseProduct() {
  fireEvent.change(
    await screen.findByRole("textbox", {
      name: en.listings.attach.searchPlaceholder,
    }),
    {
      target: { value: "Samsung" },
    },
  );
  fireEvent.click(await screen.findByRole("option", { name: "Samsung RT38 fridge" }));
}

beforeEach(() => {
  mocks.getSession.mockResolvedValue(detail);
  mocks.suggestProducts.mockResolvedValue([
    {
      entity_id: productId,
      entity_kind: "product",
      title: "Samsung RT38 fridge",
    },
  ]);
  mocks.submit.mockResolvedValue({
    session_id: detail.id,
    listing_id: "draft-listing",
    listing_status: "draft",
    session_status: "pending_admin_review",
    already_submitted: false,
  });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("requires the vendor's explicit catalogue choice and submits it for human review", async () => {
  render(review());
  const submit = await screen.findByTestId("intake-submit");
  expect(submit.hasAttribute("disabled")).toBe(true);
  expect(mocks.submit).not.toHaveBeenCalled();
  await chooseProduct();
  expect(submit.hasAttribute("disabled")).toBe(false);
  mocks.getSession.mockResolvedValue({
    ...detail,
    status: "pending_admin_review",
    submittable: false,
    listing_id: "draft-listing",
  });
  fireEvent.click(submit);
  await waitFor(() => expect(mocks.submit).toHaveBeenCalledExactlyOnceWith(detail.id, productId));
  await screen.findByText(en.intake.detail.submitted);
  expect(mocks.patchDraft).not.toHaveBeenCalled();
});

it("keeps submission disabled when no catalogue match is found", async () => {
  mocks.suggestProducts.mockResolvedValue([]);
  render(review());
  fireEvent.change(
    await screen.findByRole("textbox", {
      name: en.listings.attach.searchPlaceholder,
    }),
    {
      target: { value: "Unknown fridge" },
    },
  );
  await waitFor(() => expect(mocks.suggestProducts).toHaveBeenCalledWith("Unknown fridge"));
  await screen.findByText(en.listings.attach.empty);
  expect(screen.getByTestId("intake-submit").hasAttribute("disabled")).toBe(true);
  expect(mocks.submit).not.toHaveBeenCalled();
});

it("clears a catalogue choice when the vendor opens a different intake session", async () => {
  const { rerender } = render(review());
  await chooseProduct();
  expect(screen.getByTestId("intake-submit").hasAttribute("disabled")).toBe(false);
  mocks.getSession.mockResolvedValue({ ...detail, id: "session-two" });
  rerender(review("session-two"));
  await waitFor(() => expect(mocks.getSession).toHaveBeenCalledWith("session-two"));
  await screen.findByRole("textbox", {
    name: en.listings.attach.searchPlaceholder,
  });
  expect(screen.getByTestId("intake-submit").hasAttribute("disabled")).toBe(true);
  expect(mocks.submit).not.toHaveBeenCalled();
});
