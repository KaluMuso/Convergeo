// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ShopLayout from "./layout";

vi.mock("@vergeo/i18n", () => ({
  loadNamespace: vi.fn().mockResolvedValue({}),
}));

vi.mock("@vergeo/ui/src/icons", () => ({
  IconAccount: () => null,
  IconAsk: () => null,
  IconCart: () => null,
  IconHome: () => null,
  IconOrders: () => null,
  IconSearch: () => null,
}));

vi.mock("next-intl", () => ({
  createTranslator: () => (key: string) => key,
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn().mockResolvedValue({ common: {} }),
  setRequestLocale: vi.fn(),
}));

vi.mock("./_components/bottom-nav-client", () => ({
  BottomNavClient: () => <div data-testid="bottom-nav" />,
}));

vi.mock("./_components/install-prompt", () => ({
  default: () => <div data-testid="pwa-update-prompt" />,
}));

vi.mock("./_components/mobile-header-search", () => ({
  MobileHeaderSearch: () => <div data-testid="mobile-search" />,
}));

vi.mock("../_components/top-utility-bar-slot", () => ({
  TopUtilityBarSlot: () => <div data-testid="top-utility-bar" />,
}));

vi.mock("./_components/service-info-bar", () => ({
  ServiceInfoBar: () => <div data-testid="service-info" />,
}));

vi.mock("./_components/shop-header", () => ({
  ShopHeader: () => <header data-testid="shop-header" />,
}));

vi.mock("./_components/cart/lazy-cart-host-slot", () => ({
  LazyCartHostSlot: () => <div data-testid="cart-host-slot" />,
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ShopLayout PWA updates", () => {
  it("mounts the existing user-triggered service-worker update prompt", async () => {
    render(
      await ShopLayout({
        children: <p>Shop content</p>,
        params: Promise.resolve({ locale: "en" }),
      }),
    );

    expect(screen.getByTestId("pwa-update-prompt")).toBeInTheDocument();
    expect(screen.getByTestId("cart-host-slot")).toBeInTheDocument();
    expect(screen.getByText("Shop content")).toBeInTheDocument();
  });
});
