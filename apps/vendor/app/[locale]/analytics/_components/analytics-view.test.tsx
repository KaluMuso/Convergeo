import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider, createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import bem from "../../../../../../packages/i18n/messages/bem/vendor.json";
import common from "../../../../../../packages/i18n/messages/en/common.json";
import en from "../../../../../../packages/i18n/messages/en/vendor.json";
import fr from "../../../../../../packages/i18n/messages/fr/vendor.json";
import nya from "../../../../../../packages/i18n/messages/nya/vendor.json";
import zh from "../../../../../../packages/i18n/messages/zh/vendor.json";

import { AnalyticsView } from "./analytics-view";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "synthetic" },
    loading: false,
  }),
}));
vi.mock("../_lib/analytics-client", () => ({
  createAnalyticsClient: () => ({ get }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function show(events: number, ratio: number | null) {
  get.mockResolvedValue({
    window: 7,
    days: ["2026-10-02"],
    sales_ngwee_by_day: [12345],
    orders_by_day: [3],
    cart_activity_events_by_day: [events],
    order_activity_ratio: {
      orders_total: 3,
      cart_activity_events_total: events,
      orders_per_100_cart_activity_events: ratio,
    },
    views_by_day: [999],
    top_listings: [],
    conversion_hint: {
      orders_total: 999,
      views_total: 999,
      conversion_pct: 999,
    },
  });
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor: { analytics: en.analytics }, common }}>
      <AnalyticsView />
    </NextIntlClientProvider>,
  );
}

describe("rendered analytics definitions", () => {
  it("uses canonical counts and labels a ratio above 100 without conversion claims", async () => {
    show(1, 300);
    await waitFor(() =>
      expect(screen.getByText("300 orders per 100 cart/checkout events")).toBeTruthy(),
    );
    expect(screen.getByText("Cart/checkout events")).toBeTruthy();
    expect(
      screen.getByText("3 non-cancelled orders; 1 cart/checkout event in this window."),
    ).toBeTruthy();
    expect(screen.queryByText(/999/)).toBeNull();
    expect(screen.queryByText("Conversion")).toBeNull();
    expect(screen.getByText(/independent totals, not a conversion cohort/)).toBeTruthy();
  });

  it("renders an unavailable ratio for no events despite positive orders", async () => {
    show(0, null);
    await waitFor(() =>
      expect(
        screen.getByText("No cart/checkout events in this window; the ratio is unavailable."),
      ).toBeTruthy(),
    );
    expect(screen.queryByText(/orders per 100/)).toBeNull();
  });

  it.each(Object.entries({ en, fr, zh, bem, nya }))(
    "renders explicit ratio definitions and ICU totals for %s",
    (locale, messages) => {
      const t = createTranslator({ locale, messages, namespace: "analytics" });
      for (const key of [
        "conversion.heading",
        "conversion.definition",
        "conversion.empty",
        "cards.views",
        "meta.description",
      ] as const) {
        expect(t(key)).not.toBe(`analytics.${key}`);
      }
      expect(t("conversion.pct", { pct: 300 })).toContain("300");
      expect(t("conversion.summary", { orders: 3, views: 1 })).toContain("3");
      expect(t("conversion.summary", { orders: 3, views: 1 })).toContain("1");
      expect(t("conversion.definition")).toContain("100");
      expect(t("conversion.pct", { pct: 300 })).not.toContain("%");
      expect(t("meta.description")).not.toMatch(
        /cart-to-order|panier-commande|购物车到订单的转化率/,
      );
    },
  );
});
