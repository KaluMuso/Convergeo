"use client";

import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const dashboardApi = createApiClient({
  baseUrl: API_BASE,
  getToken: () => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.sessionStorage.getItem("vergeo_admin_token");
  },
});

export type OrdersByStatus = {
  placed: number;
  confirmed: number;
  processing: number;
  ready: number;
  shipped: number;
  delivered: number;
  completed: number;
  cancelled: number;
};

export type PayoutLiabilities = {
  escrow_held_ngwee: number;
  released_unpaid_ngwee: number;
  total_ngwee: number;
};

export type ReconciliationTile = {
  status: string;
  report_id: string | null;
  report_date: string | null;
  has_mismatch: boolean;
};

export type CatalogCounts = {
  vendors: number;
  listings: number;
  products: number;
};

export type AiUsageTile = {
  data_available: boolean;
  flagged: boolean;
  spend_usd: number | null;
  cap_usd: number;
};

export type FunnelSnapshot = {
  checkout_started: number;
  checkout_completed: number;
  orders_placed: number;
  orders_completed: number;
};

export type DashboardData = {
  gmv_ngwee: number;
  orders_by_status: OrdersByStatus;
  payout_liabilities: PayoutLiabilities;
  reconciliation: ReconciliationTile;
  counts: CatalogCounts;
  ai_usage: AiUsageTile;
  funnel: FunnelSnapshot;
  cached_at: string;
};
