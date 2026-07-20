// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import accountMessages from "../../../../../../packages/i18n/messages/en/account.json";

import { AccountNav } from "./account-nav";
import { AccountOverview } from "./account-overview";

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/account",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@vergeo/auth/browser-client", () => ({
  createBrowserClient: () => ({
    auth: {
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
  }),
}));

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

beforeEach(() => {
  window.localStorage.clear();
});

const navLabels = {
  ariaLabel: accountMessages.title,
  overview: accountMessages.nav.overview,
  orders: accountMessages.nav.orders,
  tickets: accountMessages.nav.tickets,
  jobs: accountMessages.nav.jobs,
  saved: accountMessages.nav.saved,
  addresses: accountMessages.nav.addresses,
  preferences: accountMessages.nav.preferences,
  profile: accountMessages.nav.profile,
  privacy: accountMessages.nav.privacy,
  business: accountMessages.nav.business,
  signOut: accountMessages.nav.signOut,
  signingOut: accountMessages.nav.signingOut,
};

describe("AccountNav", () => {
  it("exposes the proposed account hub destinations including saved and sign out", () => {
    render(<AccountNav locale="en" labels={navLabels} />);

    expect(screen.getByTestId("account-nav")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: navLabels.orders })).toHaveAttribute(
      "href",
      "/en/account/orders",
    );
    expect(screen.getByRole("link", { name: navLabels.saved })).toHaveAttribute(
      "href",
      "/en/wishlist",
    );
    expect(screen.getByRole("link", { name: navLabels.preferences })).toHaveAttribute(
      "href",
      "/en/account/preferences",
    );
    expect(screen.getByTestId("account-sign-out")).toHaveTextContent(navLabels.signOut);
  });

  it("supports keyboard focus across nav links", async () => {
    const user = userEvent.setup();
    render(<AccountNav locale="en" labels={navLabels} />);

    await user.tab();
    expect(screen.getByRole("link", { name: navLabels.overview })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: navLabels.orders })).toHaveFocus();
  });
});

describe("AccountOverview", () => {
  it("renders practical hub cards without inventing metrics", () => {
    render(
      <AccountOverview
        locale="en"
        labels={{
          title: accountMessages.hub.title,
          description: accountMessages.hub.description,
          ordersTitle: accountMessages.hub.ordersTitle,
          ordersBody: accountMessages.hub.ordersBody,
          ordersCta: accountMessages.hub.ordersCta,
          savedTitle: accountMessages.hub.savedTitle,
          savedEmpty: accountMessages.hub.savedEmpty,
          savedCount: accountMessages.hub.savedCount,
          savedCta: accountMessages.hub.savedCta,
          recentTitle: accountMessages.hub.recentTitle,
          recentEmpty: accountMessages.hub.recentEmpty,
          recentCta: accountMessages.hub.recentCta,
          addressesTitle: accountMessages.hub.addressesTitle,
          addressesBody: accountMessages.hub.addressesBody,
          addressesCta: accountMessages.hub.addressesCta,
          preferencesTitle: accountMessages.hub.preferencesTitle,
          preferencesBody: accountMessages.hub.preferencesBody,
          preferencesCta: accountMessages.hub.preferencesCta,
          helpTitle: accountMessages.hub.helpTitle,
          helpBody: accountMessages.hub.helpBody,
          helpCta: accountMessages.hub.helpCta,
          deviceNote: accountMessages.hub.deviceNote,
        }}
      />,
    );

    expect(screen.getByTestId("account-overview")).toBeInTheDocument();
    expect(screen.getByTestId("account-hub-orders")).toHaveTextContent(
      accountMessages.hub.ordersTitle,
    );
    expect(screen.getByTestId("account-hub-saved")).toHaveTextContent(
      accountMessages.hub.savedEmpty,
    );
    expect(screen.getByText(accountMessages.hub.deviceNote)).toBeInTheDocument();
  });
});

describe("account i18n sitemap keys", () => {
  it("includes hub, saved, recent, and expanded nav", () => {
    expect(accountMessages.nav.overview).toBeTruthy();
    expect(accountMessages.nav.signOut).toBeTruthy();
    expect(accountMessages.saved.disclaimer.toLowerCase()).toContain("does not reserve");
    expect(accountMessages.recent.privacyNote.toLowerCase()).toContain("browser");
  });
});
