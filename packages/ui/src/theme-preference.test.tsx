// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "./theme-provider";
import { ThemePreference } from "./theme-preference";
import { THEME_STORAGE_KEY } from "./theme-script";

function mockMatchMedia(matches: boolean) {
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
  cleanup();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

beforeEach(() => {
  mockMatchMedia(false);
});

describe("ThemePreference", () => {
  it("defaults to light and persists system when selected", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemePreference
          label="Display"
          description="Choose a theme"
          lightLabel="Light"
          darkLabel="Dark"
          systemLabel="System"
        />
      </ThemeProvider>,
    );

    expect(screen.getByLabelText("Light")).toBeChecked();

    await user.click(screen.getByLabelText("System"));
    expect(screen.getByLabelText("System")).toBeChecked();
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("system");
  });

  it("can select dark", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemePreference label="Display" lightLabel="Light" darkLabel="Dark" systemLabel="System" />
      </ThemeProvider>,
    );

    await user.click(screen.getByLabelText("Dark"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });
});
