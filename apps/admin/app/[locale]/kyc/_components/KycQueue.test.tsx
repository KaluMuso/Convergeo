// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KycQueue } from "./KycQueue";

import type { Root } from "react-dom/client";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

vi.mock("next-intl", () => {
  const t = (key: string) => key;
  return { useTranslations: () => t };
});

vi.mock("./api", () => ({
  kycApi: {
    request: vi.fn(async () => [
      {
        vendor_id: "v-1",
        display_name: "Kabulonga Tech Hub",
        slug: "kabulonga-tech-hub",
        tier: 2,
        updated_at: "2026-11-24T08:00:00Z",
        sla_badge: "due_soon",
        kyc_record_id: "k-1",
      },
    ]),
  },
}));

vi.mock("./KycReviewDialog", () => ({ KycReviewDialog: () => null }));

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
});

describe("KycQueue", () => {
  it("renders phone cards alongside the wide-screen table for each pending vendor", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<KycQueue locale="en" />);
    });
    const cards = container.querySelector("[data-testid='kyc-queue-cards']");
    expect(cards?.className).toContain("sm:hidden");
    expect(cards?.querySelectorAll("li")).toHaveLength(1);
    expect(cards?.textContent).toContain("Kabulonga Tech Hub");
    expect(cards?.querySelector("button")?.textContent).toBe("review");
    expect(container.querySelector("table")?.parentElement?.className).toContain("sm:block");
  });
});
