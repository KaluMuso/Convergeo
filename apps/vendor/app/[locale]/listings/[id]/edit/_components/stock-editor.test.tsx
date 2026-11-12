import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError } from "@vergeo/config";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StockEditor } from "./stock-editor";

import type { createManageClient, StockContext } from "../_lib/manage-client";

const { translate } = vi.hoisted(() => ({ translate: (key: string) => key }));
vi.mock("next-intl", () => ({ useTranslations: () => translate }));

const snapshot: StockContext = {
  listing_id: "listing",
  branch_tracked: true,
  stock_qty: null,
  stock_mode: "tracked",
  sale_unit: "each",
  unit_step_milli: 1000,
  branches: [{ location_id: "branch-a", label: "Branch A", stock_qty: 10, active: true }],
};

function setup() {
  const getStock = vi.fn().mockResolvedValue(snapshot);
  const adjustStock = vi.fn();
  const client = { getStock, adjustStock } as unknown as ReturnType<typeof createManageClient>;
  render(<StockEditor listingId="listing" ownerId="owner" client={client} />);
  return { getStock, adjustStock };
}

async function fill() {
  fireEvent.change(await screen.findByLabelText("branch"), { target: { value: "branch-a" } });
  fireEvent.change(screen.getByLabelText("delta"), { target: { value: "-2" } });
  fireEvent.change(screen.getByLabelText("reason"), { target: { value: "damaged" } });
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("intentional stock adjustment", () => {
  it("retries the exact stored operation after an uncertain response", async () => {
    const { adjustStock } = setup();
    adjustStock.mockRejectedValueOnce(
      new ApiError("stock.unavailable", "unavailable", { status: 503 }),
    );
    adjustStock.mockResolvedValueOnce({
      ok: true,
      old_qty: 10,
      new_qty: 8,
      operation_id: "recorded",
    });
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "apply" }));
    await screen.findByText("retrySame");
    expect(screen.queryByRole("status")).toBeNull();
    const first = adjustStock.mock.calls[0]?.[1];
    expect(JSON.parse(sessionStorage.getItem("stock-adjustment:owner:listing") ?? "null")).toEqual(
      first,
    );
    fireEvent.click(screen.getByRole("button", { name: "retry" }));
    await screen.findByRole("status");
    expect(adjustStock.mock.calls[1]?.[1]).toEqual(first);
    expect(first).toMatchObject({ delta: -2, reason: "damaged", location_id: "branch-a" });
    expect(sessionStorage.getItem("stock-adjustment:owner:listing")).toBeNull();
  });

  it("shows a rejected save, refetches stock and never shows success", async () => {
    const { getStock, adjustStock } = setup();
    adjustStock.mockRejectedValueOnce(
      new ApiError("stock.insufficient", "rejected", { status: 409 }),
    );
    await fill();
    getStock.mockResolvedValue({
      ...snapshot,
      branches: [{ ...snapshot.branches[0], stock_qty: 1 }],
    });
    fireEvent.click(screen.getByRole("button", { name: "apply" }));
    await screen.findByText("conflict");
    await waitFor(() => expect(getStock).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("option", { name: /Branch A.*1/ })).toBeTruthy();
    expect(sessionStorage.getItem("stock-adjustment:owner:listing")).toBeNull();
  });
});
