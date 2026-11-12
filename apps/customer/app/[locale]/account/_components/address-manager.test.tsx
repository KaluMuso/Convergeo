// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@vergeo/config";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { deleteAddress, listAddresses, refresh } = vi.hoisted(() => ({
  deleteAddress: vi.fn(),
  listAddresses: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

vi.mock("./account-api", () => ({
  createAccountApiClient: () => ({ deleteAddress, listAddresses }),
}));

import { AddressManager, type AddressManagerLabels } from "./address-manager";

const labels = {
  add: "Add address",
  edit: "Edit address",
  emptyTitle: "No saved addresses",
  emptyBody: "Add one",
  countLabel: "1 saved address",
  coordsTemplate: "{lat}, {lng}",
  delete: "Delete address",
  deleteConfirmTitle: "Delete this address?",
  deleteConfirmBody: "This address will be removed from your account.",
  deleteBlocked: "This address is on an order that has not been delivered yet.",
  deleteFailed: "Could not delete the address. Please try again.",
  saved: "Address saved",
  saving: "Saving…",
  cancel: "Cancel",
} as unknown as AddressManagerLabels;

const address = {
  id: "addr-1",
  label: "Checkout",
  landmark: "Kabwata market",
  lat: null,
  lng: null,
  phone: null,
};

async function confirmDelete() {
  const user = userEvent.setup();
  render(
    <AddressManager locale="en" accessToken="tok" initialAddresses={[address]} labels={labels} />,
  );
  await user.click(screen.getByRole("button", { name: labels.delete }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: labels.delete }));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AddressManager delete", () => {
  it("explains that an address on an undelivered order cannot be deleted", async () => {
    deleteAddress.mockRejectedValue(
      new ApiError("account.address_in_use", "server detail", { status: 409 }),
    );

    await confirmDelete();

    expect(await screen.findByTestId("address-delete-error")).toHaveTextContent(
      labels.deleteBlocked,
    );
    expect(screen.queryByText("server detail")).not.toBeInTheDocument();
    // The address is still listed and nothing claims it was saved.
    expect(screen.getByText("Kabwata market")).toBeInTheDocument();
    expect(screen.queryByText(labels.saved)).not.toBeInTheDocument();
    expect(listAddresses).not.toHaveBeenCalled();
  });

  it("reports any other failure with translated copy instead of throwing", async () => {
    deleteAddress.mockRejectedValue(new Error("network down"));

    await confirmDelete();

    expect(await screen.findByTestId("address-delete-error")).toHaveTextContent(
      labels.deleteFailed,
    );
  });

  it("removes the address when the API accepts the delete", async () => {
    deleteAddress.mockResolvedValue(undefined);
    listAddresses.mockResolvedValue([]);

    await confirmDelete();

    await waitFor(() => expect(screen.getByText(labels.saved)).toBeInTheDocument());
    expect(deleteAddress).toHaveBeenCalledWith("addr-1");
    expect(screen.queryByTestId("address-delete-error")).not.toBeInTheDocument();
  });
});
