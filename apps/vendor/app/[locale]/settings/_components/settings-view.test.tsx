import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";

import vendor from "../../../../../../packages/i18n/messages/en/vendor.json";

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

it("renders account, notifications, payout method and language sections", () => {
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor }}>
      <SettingsView locale="en" />
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
