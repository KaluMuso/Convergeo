// @vitest-environment jsdom

import { ApiError } from "@vergeo/config";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OffersBoard } from "./OffersBoard";

import type { AdminOffer } from "./api";

const mocks = vi.hoisted(() => ({
  t: (key: string) => key,
  listOffers: vi.fn(),
  setOfferPaused: vi.fn(),
  success: vi.fn(),
}));

vi.mock("next-intl", () => ({
  // Stable like next-intl's real translator (a new function per render would
  // re-run the load effect forever).
  useTranslations: () => mocks.t,
}));
vi.mock("@vergeo/ui/src/toast", () => ({ notify: { success: mocks.success } }));
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, listOffers: mocks.listOffers, setOfferPaused: mocks.setOfferPaused };
});
vi.mock("../../../../lib/access-token", () => ({ getBrowserAccessToken: vi.fn(async () => "t") }));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const roots: ReturnType<typeof createRoot>[] = [];

function offer(overrides: Partial<AdminOffer> = {}): AdminOffer {
  return {
    id: "o1",
    vendor_id: "v1",
    vendor_name: "Shop A",
    offer_type: "bundle",
    title: "Kit + brush",
    status: "active",
    starts_at: "2026-11-01T00:00:00+00:00",
    ends_at: null,
    gift_stock_total: null,
    gift_stock_reserved: 0,
    per_customer_limit: 2,
    max_applications_per_order: 1,
    paused_by_admin: false,
    admin_note: null,
    live: true,
    cart_applicable: true,
    ...overrides,
  };
}

async function mount() {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  roots.push(root);
  await act(async () => {
    root.render(<OffersBoard locale="en" />);
  });
  return host;
}

beforeEach(() => {
  mocks.listOffers.mockReset();
  mocks.setOfferPaused.mockReset();
  mocks.success.mockReset();
});

afterEach(() => {
  act(() => roots.forEach((root) => root.unmount()));
  roots.length = 0;
  document.body.innerHTML = "";
});

describe("OffersBoard", () => {
  it("lists offers with vendor, limit and live state", async () => {
    mocks.listOffers.mockResolvedValue({ items: [offer()], truncated: false });
    const host = await mount();
    const card = host.querySelector('[data-testid="admin-offer"]')!;
    expect(card.textContent).toContain("Kit + brush");
    expect(card.textContent).toContain("vendor");
    expect(card.textContent).toContain("state.live");
    expect(card.textContent).toContain("perCustomer");
    expect(card.textContent).toContain("actions.pause");
  });

  it("reloads with the chosen filter", async () => {
    mocks.listOffers.mockResolvedValue({ items: [], truncated: false });
    const host = await mount();
    expect(host.textContent).toContain("empty");
    const select = host.querySelector("select") as HTMLSelectElement;
    await act(async () => {
      select.value = "admin_paused";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(mocks.listOffers).toHaveBeenLastCalledWith(
      expect.objectContaining({ state: "admin_paused" }),
    );
  });

  it("pauses with a note and updates the card", async () => {
    mocks.listOffers.mockResolvedValue({ items: [offer()], truncated: false });
    mocks.setOfferPaused.mockResolvedValue(
      offer({ paused_by_admin: true, live: false, admin_note: "abuse" }),
    );
    const host = await mount();
    await act(async () => {
      (host.querySelector('[data-testid="admin-offer"] button') as HTMLButtonElement).click();
    });
    const textarea = document.body.querySelector("textarea") as HTMLTextAreaElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      setter.call(textarea, "  abuse  ");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      (
        document.body.querySelector('[data-testid="offer-pause-confirm"]') as HTMLButtonElement
      ).click();
    });
    expect(mocks.setOfferPaused).toHaveBeenCalledWith("o1", true, "abuse");
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    expect(host.textContent).toContain("state.admin_paused");
    expect(host.textContent).toContain("actions.unpause");
    expect(mocks.success).toHaveBeenCalledWith("pausedToast");
  });

  it("keeps the dialog open with an error when the API refuses", async () => {
    mocks.listOffers.mockResolvedValue({ items: [offer()], truncated: false });
    mocks.setOfferPaused.mockRejectedValue(new ApiError("forbidden", "forbidden", { status: 403 }));
    const host = await mount();
    await act(async () => {
      (host.querySelector('[data-testid="admin-offer"] button') as HTMLButtonElement).click();
    });
    await act(async () => {
      (
        document.body.querySelector('[data-testid="offer-pause-confirm"]') as HTMLButtonElement
      ).click();
    });
    expect(document.body.querySelector('[role="alert"]')?.textContent).toBe("actions.failure");
    expect(host.textContent).toContain("state.live");
  });

  it("shows the permission-denied state on 403", async () => {
    mocks.listOffers.mockRejectedValue(new ApiError("forbidden", "forbidden", { status: 403 }));
    const host = await mount();
    expect(host.textContent).toContain("permissionDenied");
    expect(host.querySelector('[data-testid="admin-offer"]')).toBeNull();
  });
});
