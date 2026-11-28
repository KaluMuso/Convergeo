// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "./error";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const mocks = vi.hoisted(() => ({ report: vi.fn(), reload: vi.fn() }));

vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("next/navigation", () => ({ useParams: () => ({ locale: "en" }) }));
vi.mock("@vergeo/observability", () => ({ useReportClientError: mocks.report }));
vi.mock("../../lib/chunk-reload", () => ({ reloadOnceForChunkError: mocks.reload }));

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  mocks.report.mockClear();
  mocks.reload.mockClear();
});

describe("admin route error boundary", () => {
  it("explains the failure, reports it as an admin route error and retries on demand", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    const reset = vi.fn();
    const error = Object.assign(new Error("boom"), { digest: "d1" });
    await act(async () => root?.render(<ErrorBoundary error={error} reset={reset} />));

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("errorPage.heading");
    expect(container.textContent).toContain("errorPage.body");
    expect(mocks.report).toHaveBeenCalledWith(
      error,
      { boundary: "route", application: "admin" },
      expect.objectContaining({ locale: "en" }),
    );
    expect(mocks.reload).toHaveBeenCalledWith(error);
    await act(async () => container?.querySelector("button")?.click());
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
