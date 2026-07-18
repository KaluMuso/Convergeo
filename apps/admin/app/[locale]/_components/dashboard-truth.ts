import type {
  DashboardData,
  FunnelSnapshot,
  OrdersByStatus,
  PayoutLiabilities,
  ReconciliationTile,
} from "./api";

/** True when every order-status bucket is zero (no orders in pipeline). */
export function isOrdersPipelineEmpty(orders: OrdersByStatus): boolean {
  return Object.values(orders).every((count) => count === 0);
}

/** True when funnel conversion counters are all zero. */
export function isFunnelEmpty(funnel: FunnelSnapshot): boolean {
  return (
    funnel.checkout_started === 0 &&
    funnel.checkout_completed === 0 &&
    funnel.orders_placed === 0 &&
    funnel.orders_completed === 0
  );
}

/** True when ledger-derived liabilities are all zero (honest empty, not fabricated). */
export function isPayoutLiabilitiesEmpty(liabilities: PayoutLiabilities): boolean {
  return (
    liabilities.escrow_held_ngwee === 0 &&
    liabilities.released_unpaid_ngwee === 0 &&
    liabilities.total_ngwee === 0
  );
}

/**
 * Reconciliation with no report must not render as "Balanced".
 * API historically returns status=green when report_id is null — UI treats that as unknown.
 */
export function reconciliationDisplayStatus(
  reconciliation: ReconciliationTile,
): "green" | "red" | "unknown" {
  if (reconciliation.has_mismatch || reconciliation.status === "red") {
    return "red";
  }
  if (!reconciliation.report_id || !reconciliation.report_date) {
    return "unknown";
  }
  return "green";
}

/**
 * Platform traffic/money tiles are "empty" when GMV, orders, funnel, and liabilities
 * are all zero. Catalog counts may still be non-zero (seeded demo) — that is called out separately.
 */
export function isAnalyticsTrafficEmpty(data: DashboardData): boolean {
  return (
    data.gmv_ngwee === 0 &&
    isOrdersPipelineEmpty(data.orders_by_status) &&
    isFunnelEmpty(data.funnel) &&
    isPayoutLiabilitiesEmpty(data.payout_liabilities)
  );
}
