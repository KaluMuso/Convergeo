// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import common from "../../../../../../packages/i18n/messages/en/common.json";
import vendor from "../../../../../../packages/i18n/messages/en/vendor.json";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";

import { SettingsView } from "./settings-view";

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "t", user: { id: "u" } },
    user: { id: "u", email: "shop@example.com", phone: "" },
    loading: false,
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/settings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

afterEach(cleanup);

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

it("renders account, notifications, payout method and language sections", () => {
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor, common }}>
      <ThemeProvider>
        <SettingsView locale="en" />
      </ThemeProvider>
    </NextIntlClientProvider>,
  );
  for (const id of ["account", "notifications", "payout", "language"]) {
    expect(screen.getByTestId(`settings-${id}`)).toBeTruthy();
  }
  expect(screen.getByTestId("settings-contact").textContent).toBe("shop@example.com");
  expect(screen.getByTestId("settings-sign-out")).toBeTruthy();
  const select = screen.getByTestId("settings-locale") as HTMLSelectElement;
  expect(select.value).toBe("en");
  expect(select.options.length).toBe(5);
});
