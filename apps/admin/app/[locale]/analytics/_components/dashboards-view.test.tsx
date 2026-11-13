// @vitest-environment jsdom
import { NextIntlClientProvider } from "next-intl";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import admin from "../../../../../../packages/i18n/messages/en/admin.json";

vi.mock("../../_components/api", () => ({ dashboardApi: { request: vi.fn() } }));
vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: async () => "t" }));

import { DashboardBody } from "./dashboards-view";

import type { RevenueData, UsersData, VendorsData } from "./dashboards-data";

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
