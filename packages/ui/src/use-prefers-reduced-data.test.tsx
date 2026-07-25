// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePrefersReducedData } from "./use-prefers-reduced-data";

function setConnection(saveData: boolean | undefined) {
  Object.defineProperty(window.navigator, "connection", {
    configurable: true,
    value: saveData === undefined ? undefined : { saveData },
  });
}

function mockMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Object.defineProperty(window.navigator, "connection", { configurable: true, value: undefined });
});

describe("usePrefersReducedData", () => {
  it("is false when neither saveData nor the media query is set", () => {
    setConnection(false);
    mockMatchMedia(false);
    const { result } = renderHook(() => usePrefersReducedData());
    expect(result.current).toBe(false);
  });

  it("is true when connection.saveData is set", () => {
    setConnection(true);
    mockMatchMedia(false);
    const { result } = renderHook(() => usePrefersReducedData());
    expect(result.current).toBe(true);
  });

  it("is true when prefers-reduced-data:reduce matches", () => {
    setConnection(false);
    mockMatchMedia(true);
    const { result } = renderHook(() => usePrefersReducedData());
    expect(result.current).toBe(true);
  });

  it("reacts to media-query changes", () => {
    setConnection(false);
    let handler: (() => void) | null = null;
    const mq = {
      matches: false,
      media: "(prefers-reduced-data: reduce)",
      onchange: null,
      addEventListener: (_event: string, cb: () => void) => {
        handler = cb;
      },
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    };
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => mq),
    );

    const { result } = renderHook(() => usePrefersReducedData());
    expect(result.current).toBe(false);

    act(() => {
      mq.matches = true;
      handler?.();
    });
    expect(result.current).toBe(true);
  });
});
