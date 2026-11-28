// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";

import vendor from "../../../../../../packages/i18n/messages/en/vendor.json";

import { DeliveryTermsCard } from "./delivery-terms-card";

import type { DeliveryTerms, DeliveryTermsClient } from "../_lib/delivery-terms-client";

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "t" }, loading: false }),
}));

afterEach(cleanup);

const OFF: DeliveryTerms = { free_delivery_all: false, free_delivery_method: "platform_courier" };

function setup(initial: DeliveryTerms = OFF, updateImpl?: DeliveryTermsClient["update"]) {
  const client = {
    get: vi.fn().mockResolvedValue(initial),
    update:
      updateImpl ?? vi.fn(async (changes: Partial<DeliveryTerms>) => ({ ...initial, ...changes })),
  } as unknown as DeliveryTermsClient;
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor }}>
      <DeliveryTermsCard client={client} />
    </NextIntlClientProvider>,
  );
  return client;
}

it("turning free delivery on needs an explicit confirm and says who pays", async () => {
  const client = setup();
  const toggle = await screen.findByTestId("delivery-all-toggle");
  fireEvent.click(toggle);
  expect(client.update).not.toHaveBeenCalled();
  expect(screen.getByTestId("delivery-confirm")).toHaveTextContent(
    "taken from your earnings once the order is complete",
  );
  fireEvent.click(screen.getByTestId("delivery-confirm-yes"));
  await waitFor(() => expect(client.update).toHaveBeenCalledWith({ free_delivery_all: true }));
  expect(await screen.findByText("Saved. This applies to new orders.")).toBeTruthy();
});

it("cancelling the confirm changes nothing", async () => {
  const client = setup();
  fireEvent.click(await screen.findByTestId("delivery-all-toggle"));
  fireEvent.click(screen.getByTestId("delivery-confirm-no"));
  expect(client.update).not.toHaveBeenCalled();
  expect(screen.queryByTestId("delivery-confirm")).toBeNull();
  expect((screen.getByTestId("delivery-all-toggle") as HTMLInputElement).checked).toBe(false);
});

it("turning free delivery off saves straight away (the cost moves back to the customer)", async () => {
  const client = setup({ free_delivery_all: true, free_delivery_method: "platform_courier" });
  const toggle = (await screen.findByTestId("delivery-all-toggle")) as HTMLInputElement;
  expect(toggle.checked).toBe(true);
  fireEvent.click(toggle);
  await waitFor(() => expect(client.update).toHaveBeenCalledWith({ free_delivery_all: false }));
});

it("switching to a courier confirms; switching to own delivery saves directly", async () => {
  const client = setup({ free_delivery_all: false, free_delivery_method: "self_delivery" });
  fireEvent.click(await screen.findByTestId("delivery-method-platform_courier"));
  expect(client.update).not.toHaveBeenCalled();
  expect(screen.getByTestId("delivery-confirm")).toHaveTextContent("Switch to a Vergeo5 courier?");
  fireEvent.click(screen.getByTestId("delivery-confirm-yes"));
  await waitFor(() =>
    expect(client.update).toHaveBeenCalledWith({ free_delivery_method: "platform_courier" }),
  );
  fireEvent.click(await screen.findByTestId("delivery-method-self_delivery"));
  await waitFor(() =>
    expect(client.update).toHaveBeenLastCalledWith({ free_delivery_method: "self_delivery" }),
  );
});

it("shows an error and keeps the old terms when saving fails", async () => {
  const failing = vi.fn().mockRejectedValue({
    details: { message_key: "vendor.deliveryTerms.errors.rateLimited" },
  });
  setup(OFF, failing as unknown as DeliveryTermsClient["update"]);
  fireEvent.click(await screen.findByTestId("delivery-all-toggle"));
  fireEvent.click(screen.getByTestId("delivery-confirm-yes"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Too many changes");
  expect((screen.getByTestId("delivery-all-toggle") as HTMLInputElement).checked).toBe(false);
});

it("shows a load error instead of guessing the current terms", async () => {
  const client = {
    get: vi.fn().mockRejectedValue(new Error("boom")),
    update: vi.fn(),
  } as unknown as DeliveryTermsClient;
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor }}>
      <DeliveryTermsCard client={client} />
    </NextIntlClientProvider>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("couldn't load");
  expect(screen.queryByTestId("delivery-all-toggle")).toBeNull();
});
