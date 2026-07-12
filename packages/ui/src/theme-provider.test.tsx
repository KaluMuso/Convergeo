// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider, useTheme } from "./theme-provider";
import { resolveInitialTheme, THEME_SCRIPT, THEME_STORAGE_KEY } from "./theme-script";
import { ThemeToggle } from "./theme-toggle";

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

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

describe("resolveInitialTheme (no-FOUC logic)", () => {
  it("honours an explicit stored choice over OS preference", () => {
    expect(resolveInitialTheme("dark", false)).toBe("dark");
    expect(resolveInitialTheme("light", true)).toBe("light");
  });

  it("falls back to OS preference when unset or 'system'", () => {
    expect(resolveInitialTheme(null, true)).toBe("dark");
    expect(resolveInitialTheme(null, false)).toBe("light");
    expect(resolveInitialTheme("system", true)).toBe("dark");
  });
});

describe("THEME_SCRIPT", () => {
  it("references the shared storage key and is a self-contained IIFE", () => {
    expect(THEME_SCRIPT).toContain(THEME_STORAGE_KEY);
    expect(THEME_SCRIPT).toContain("dataset.theme");
    expect(THEME_SCRIPT).toContain("prefers-color-scheme");
    expect(THEME_SCRIPT.startsWith("(function()")).toBe(true);
  });
});

describe("ThemeProvider / useTheme", () => {
  it("defaults to system and resolves from prefers-color-scheme", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe("system");
    expect(result.current.resolvedTheme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("reads a persisted choice on mount", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe("dark");
    expect(result.current.resolvedTheme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("persists and applies an explicit choice via setTheme", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setTheme("dark"));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(result.current.resolvedTheme).toBe("dark");
  });

  it("cycles light → dark → system", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setTheme("light"));
    expect(result.current.theme).toBe("light");
    act(() => result.current.cycleTheme());
    expect(result.current.theme).toBe("dark");
    act(() => result.current.cycleTheme());
    expect(result.current.theme).toBe("system");
    act(() => result.current.cycleTheme());
    expect(result.current.theme).toBe("light");
  });

  it("throws when useTheme is used outside a provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useTheme())).toThrow(/ThemeProvider/);
    spy.mockRestore();
  });
});

describe("ThemeToggle", () => {
  it("announces the current mode and cycles on click", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(
      <ThemeProvider>
        <ThemeToggle label="Theme" lightLabel="Light" darkLabel="Dark" systemLabel="System" />
      </ThemeProvider>,
    );
    const button = screen.getByRole("button", { name: "Theme: Light" });
    await user.click(button);
    expect(screen.getByRole("button", { name: "Theme: Dark" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
