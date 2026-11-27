// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveErrorPageCopy, resolveLocaleFromPathname } from "../lib/error-page-copy";

import GlobalError from "./global-error";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const mocks = vi.hoisted(() => ({ report: vi.fn(), reload: vi.fn() }));
vi.mock("@vergeo/observability", () => ({ useReportClientError: mocks.report }));
vi.mock("../lib/chunk-reload", () => ({ reloadOnceForChunkError: mocks.reload }));
vi.mock("./globals.css", () => ({}));

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  mocks.report.mockClear();
  window.history.replaceState({}, "", "/");
});

describe("admin global error boundary", () => {
  it("renders translated copy, reports as admin/global and retries", async () => {
    window.history.replaceState({}, "", "/fr/orders");
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    const reset = vi.fn();
    const error = new Error("layout exploded");
    // <html> cannot nest in a div: render only the inner document for assertions.
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await act(async () => root?.render(<GlobalError error={error} reset={reset} />));
    spy.mockRestore();
    const copy = resolveErrorPageCopy("fr");
    expect(document.body.textContent).toContain(copy.heading);
    expect(mocks.report).toHaveBeenCalledWith(
      error,
      { boundary: "global", application: "admin" },
      expect.objectContaining({ locale: "fr" }),
    );
    await act(async () => document.querySelector("button")?.click());
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("falls back to English for locales without copy", () => {
    expect(resolveErrorPageCopy("zh").heading).toBe(resolveErrorPageCopy("en").heading);
    expect(resolveLocaleFromPathname("/nya/kyc")).toBe("nya");
    expect(resolveLocaleFromPathname("/nope")).toBe("en");
  });
});
