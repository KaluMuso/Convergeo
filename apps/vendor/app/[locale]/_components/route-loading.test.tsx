// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl/server", () => ({
  getTranslations: async () => (key: string) => (key === "common.loading" ? "Loading…" : key),
}));

import { RouteLoading } from "./route-loading";

afterEach(cleanup);

describe("RouteLoading", () => {
  it.each([
    ["page", "vendor-page-skeleton"],
    ["list", "vendor-list-skeleton"],
    ["dashboard", "vendor-dashboard-skeleton"],
    ["analytics", "vendor-analytics-skeleton"],
    ["order", "vendor-order-skeleton"],
  ] as const)("renders the %s skeleton with a localised status label", async (variant, testId) => {
    render(await RouteLoading({ variant }));
    expect(screen.getByTestId(testId)).toBeInTheDocument();
  });

  it("still renders when the request locale is unavailable", async () => {
    vi.resetModules();
    vi.doMock("next-intl/server", () => ({
      getTranslations: async () => {
        throw new Error("no request locale");
      },
    }));
    const { RouteLoading: Fresh } = await import("./route-loading");
    render(await Fresh({ variant: "list" }));
    expect(screen.getByTestId("vendor-list-skeleton")).toBeInTheDocument();
  });
});
