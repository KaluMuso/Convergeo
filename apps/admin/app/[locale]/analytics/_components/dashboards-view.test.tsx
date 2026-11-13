// @vitest-environment jsdom
import { NextIntlClientProvider } from "next-intl";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import admin from "../../../../../../packages/i18n/messages/en/admin.json";

vi.mock("../../_components/api", () => ({ dashboardApi: { request: vi.fn() } }));
vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: async () => "t" }));

import { DashboardBody } from "./dashboards-view";

import type {
  PerformanceData,
  PerformanceRow,
  RevenueData,
  UsersData,
  VendorsData,
} from "./dashboards-data";

function render(node: React.ReactNode): string {
  return renderToStaticMarkup(
    <NextIntlClientProvider locale="en" messages={{ admin }} timeZone="UTC">
      {node}
    </NextIntlClientProvider>,
  );
}

const range = { period: "7d", from: "2026-11-07", to: "2026-11-13" };

describe("dashboard bodies", () => {
  it("revenue shows ledger revenue as kwacha and labels order value as not revenue", () => {
    const orders = {
      placed: 4,
      paid: 3,
      cancelled: 1,
      paid_order_value_ngwee: 2_450_000,
      average_paid_order_ngwee: 1_225_000,
      payments_reconciled: true,
      payment_mismatch_days: [],
      paid_then_cancelled: 1,
    };
    const revenue = {
      commission_ngwee: 150_000,
      delivery_ngwee: 150_000,
      total_ngwee: 300_000,
      processing_fees_ngwee: 30_000,
    };
    const data: RevenueData = {
      range,
      previous_range: range,
      orders,
      previous_orders: orders,
      platform_revenue: revenue,
      previous_platform_revenue: { ...revenue, total_ngwee: 0 },
      take_rate_bps: 1224,
      refunds: { requested: 3, completed: 1, completed_ngwee: 400_000, open: 1, failed: 1 },
      daily: [],
    };
    const html = render(<DashboardBody tab="revenue" data={data} locale="en" />);
    expect(html).toContain("Platform revenue");
    expect(html).toContain("K3,000.00");
    expect(html).toContain("Not revenue");
    expect(html).toContain("No activity in this period.");
    expect(html).not.toContain('role="alert"');
  });

  it("users: activity off is explained and empty cohorts say so", () => {
    const data: UsersData = {
      range,
      previous_range: range,
      totals: { customers: 12, vendors: 3, active_vendors: 2 },
      new: { customers: 0, vendors: 0 },
      previous_new: { customers: 0, vendors: 0 },
      daily: [{ day: "2026-11-13", customers: 0, vendors: 0 }],
      activity: { enabled: false },
      cohorts: [
        { cohort: "2026-11", size: 0, retained: [0], retained_bps: [null], small_sample: true },
      ],
    };
    const html = render(<DashboardBody tab="users" data={data} locale="en" />);
    expect(html).toContain('data-testid="activity-disabled"');
    expect(html).toContain("Registered customers");
    expect(html).toContain("No activity in this period.");
  });

  it("vendors without finance hide item sales", () => {
    const data: VendorsData = {
      range,
      finance_visible: false,
      kyc: {
        current: {
          submitted: 1,
          under_review: 0,
          approved: 2,
          rejected: 0,
          suspended: 0,
          revoked: 0,
        },
        submitted: 1,
        approved: 1,
        rejected: 0,
        avg_decision_hours: 2,
      },
      vendors: {
        by_status: { draft: 0, pending_kyc: 1, active: 2, suspended: 0, suspended_compliance: 0 },
        total: 3,
        active: 2,
        new: 1,
        selling: 1,
      },
      ratings: { reviews: 2, avg_x100: 450 },
      top: [
        {
          vendor_id: "v1",
          name: "Chanda Hardware",
          paid_orders: 2,
          item_sales_ngwee: null,
          rating_count: 2,
          rating_avg_x100: 450,
        },
      ],
    };
    const html = render(<DashboardBody tab="vendors" data={data} locale="en" />);
    expect(html).toContain("Chanda Hardware");
    expect(html).toContain("4.5 (2)");
    expect(html).not.toContain("Item sales");
    expect(html).toContain("finance.read");
    expect(html).toContain("2 hours");
  });
});

function perfRow(id: string, name: string, extra: Partial<PerformanceRow> = {}): PerformanceRow {
  return {
    id,
    name,
    views: 100,
    carts: 10,
    orders: 2,
    units: 3,
    customers: 1,
    repeat_customers: 1,
    view_to_cart_bps: 1000,
    cart_to_order_bps: 2000,
    view_to_order_bps: 200,
    repeat_rate_bps: 10_000,
    item_sales_ngwee: null,
    contribution_ngwee: null,
    contribution_per_order_ngwee: null,
    ...extra,
  };
}

function perfData(finance: boolean): PerformanceData {
  const money = finance
    ? {
        item_sales_ngwee: 3_000_000,
        contribution_ngwee: 225_000,
        contribution_per_order_ngwee: 112_500,
      }
    : {};
  const card = {
    entities: 2,
    top: [perfRow("p1", "Phone One", money)],
    bottom: [perfRow("p3", "Dusty Shoe", { orders: 0, view_to_order_bps: 0, ...money })],
    hidden_gems: [],
  };
  return {
    range,
    finance_visible: finance,
    thresholds: { min_views: 20, min_orders: 2, clip_attribution_days: 7, list_size: 10 },
    funnel: {
      views: 170,
      carts: 6,
      orders: 3,
      customers: 2,
      repeat_customers: 1,
      returning_customers: 1,
      view_to_cart_bps: 353,
      cart_to_order_bps: 5000,
      view_to_order_bps: 176,
      repeat_rate_bps: 5000,
      returning_rate_bps: 5000,
    },
    contribution: finance
      ? {
          orders: 3,
          items_ngwee: 35_000,
          delivery_fee_ngwee: 3_000,
          commission_ngwee: 3_250,
          payment_fee_ngwee: 359,
          courier_cost_ngwee: 1_500,
          refunded_ngwee: 10_000,
          refund_loss_ngwee: 1_000,
          contribution_ngwee: 3_391,
          contribution_per_order_ngwee: 1_130,
          margin_bps: 892,
          negative_orders: 0,
          fee_unbooked_orders: 1,
          courier_cost_unknown_orders: 1,
        }
      : null,
    categories: card,
    products: card,
    vendors: card,
    clips: { entities: 0, top: [], bottom: [], hidden_gems: [] },
  };
}

describe("performance body", () => {
  it("ranks what to boost and uproot with contribution per order for finance", () => {
    const html = render(<DashboardBody tab="performance" data={perfData(true)} locale="en" />);
    expect(html).toContain("Top: boost what sells");
    expect(html).toContain("Bottom: attention without sales");
    expect(html).toContain("Hidden gems: sell when seen");
    expect(html).toContain("Dusty Shoe");
    expect(html).toContain("Contribution per order");
    expect(html).toContain("K11.30"); // 1,130 ngwee per order
    expect(html).toContain("K1,125.00"); // product row contribution per order
    expect(html).toContain("payment fee for 1 order");
    expect(html).toContain("K30,000.00"); // item sales, finance only
  });

  it("keeps money out for analytics.read only", () => {
    const html = render(<DashboardBody tab="performance" data={perfData(false)} locale="en" />);
    expect(html).toContain("Phone One");
    expect(html).not.toContain("K11.30");
    expect(html).not.toContain("Item sales");
    expect(html).toContain("No activity in this period.");
  });
});
