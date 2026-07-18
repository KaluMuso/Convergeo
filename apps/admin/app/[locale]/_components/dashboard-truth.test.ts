import { describe, expect, it } from "vitest";

import {
  isAnalyticsTrafficEmpty,
  isFunnelEmpty,
  isOrdersPipelineEmpty,
  isPayoutLiabilitiesEmpty,
  reconciliationDisplayStatus,
} from "./dashboard-truth";

import type { DashboardData } from "./api";

const emptyOrders = {
  placed: 0,
  confirmed: 0,
  processing: 0,
  ready: 0,
  shipped: 0,
  delivered: 0,
  completed: 0,
  cancelled: 0,
};

const emptyFunnel = {
  checkout_started: 0,
  checkout_completed: 0,
  orders_placed: 0,
  orders_completed: 0,
};

const emptyLiabilities = {
  escrow_held_ngwee: 0,
  released_unpaid_ngwee: 0,
  total_ngwee: 0,
};

function baseDashboard(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    gmv_ngwee: 0,
    orders_by_status: emptyOrders,
    payout_liabilities: emptyLiabilities,
    reconciliation: {
      status: "green",
      report_id: null,
      report_date: null,
      has_mismatch: false,
    },
    counts: { vendors: 3, listings: 134, products: 150 },
    ai_usage: { data_available: true, flagged: false, spend_usd: 0, cap_usd: 15 },
    funnel: emptyFunnel,
    cached_at: "2026-07-18T00:00:00Z",
    ...overrides,
  };
}

describe("dashboard-truth", () => {
  it("treats all-zero order buckets as empty pipeline", () => {
    expect(isOrdersPipelineEmpty(emptyOrders)).toBe(true);
    expect(isOrdersPipelineEmpty({ ...emptyOrders, placed: 1 })).toBe(false);
  });

  it("treats all-zero funnel as empty", () => {
    expect(isFunnelEmpty(emptyFunnel)).toBe(true);
    expect(isFunnelEmpty({ ...emptyFunnel, checkout_started: 2 })).toBe(false);
  });

  it("treats zero liabilities as empty ledger exposure", () => {
    expect(isPayoutLiabilitiesEmpty(emptyLiabilities)).toBe(true);
    expect(
      isPayoutLiabilitiesEmpty({
        escrow_held_ngwee: 100,
        released_unpaid_ngwee: 0,
        total_ngwee: 100,
      }),
    ).toBe(false);
  });

  it("does not treat missing reconciliation report as balanced", () => {
    expect(
      reconciliationDisplayStatus({
        status: "green",
        report_id: null,
        report_date: null,
        has_mismatch: false,
      }),
    ).toBe("unknown");

    expect(
      reconciliationDisplayStatus({
        status: "green",
        report_id: "rep-1",
        report_date: "2026-07-18",
        has_mismatch: false,
      }),
    ).toBe("green");

    expect(
      reconciliationDisplayStatus({
        status: "green",
        report_id: "rep-1",
        report_date: "2026-07-18",
        has_mismatch: true,
      }),
    ).toBe("red");
  });

  it("flags traffic-empty dashboards even when catalog seed counts exist", () => {
    expect(isAnalyticsTrafficEmpty(baseDashboard())).toBe(true);
    expect(isAnalyticsTrafficEmpty(baseDashboard({ gmv_ngwee: 5000 }))).toBe(false);
  });
});
