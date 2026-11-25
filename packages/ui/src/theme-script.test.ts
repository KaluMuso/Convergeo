// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACCENT_STORAGE_KEY } from "./accent-palette";
import { THEME_SCRIPT } from "./theme-script";

function mockMatchMedia(matches = false) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.accent;
});

beforeEach(() => {
  mockMatchMedia(false);
});

describe("THEME_SCRIPT", () => {
  it("embeds accent storage key and valid choices", () => {
    expect(THEME_SCRIPT).toContain(ACCENT_STORAGE_KEY);
    expect(THEME_SCRIPT).toContain('"blue"');
    expect(THEME_SCRIPT).toContain('dataset.accent="mono"');
  });

  it("sets data-accent from storage", () => {
    window.localStorage.setItem("vg-accent", "blue");
    // eslint-disable-next-line no-eval -- mirrors inline bootstrap execution
    eval(THEME_SCRIPT);
    expect(document.documentElement.getAttribute("data-accent")).toBe("blue");
  });

  it("falls back to mono when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    // eslint-disable-next-line no-eval -- mirrors inline bootstrap execution
    eval(THEME_SCRIPT);
    expect(document.documentElement.getAttribute("data-accent")).toBe("mono");
  });
});
