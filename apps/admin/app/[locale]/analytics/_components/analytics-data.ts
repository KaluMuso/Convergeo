/**
 * Convergeo Intelligence 1B-05: admin analytics API types and pure helpers.
 *
 * The API (`/admin/analytics/*`, 1B-04) returns aggregates only: integer counts, money in
 * integer ngwee, and rates as integer basis points (`null` below the minimum sample).
 */

export type AnalyticsTab = "overview" | "search" | "products" | "insights";

export const ANALYTICS_TABS: ReadonlyArray<{ tab: AnalyticsTab; href: string; api: string }> = [
  { tab: "overview", href: "analytics", api: "overview" },
  { tab: "search", href: "analytics/search", api: "search-demand" },
  { tab: "products", href: "analytics/products", api: "products-funnel" },
  { tab: "insights", href: "analytics/insights", api: "insights" },
];

export const RANGE_DAYS = [7, 28, 90] as const;
export type RangeDays = (typeof RANGE_DAYS)[number];

export type DateRange = { from: string; to: string };

export type Behaviour = {
  sessions: number;
  visitor_days: number;
  bounce_rate_bps: number | null;
  avg_active_span_seconds: number | null;
  searches: number;
  zero_result_share_bps: number | null;
};

export type Commercial = {
  checkouts_started: number;
  orders_placed: number;
  orders_cancelled: number;
  orders_paid: number;
  paid_checkouts: number;
  gmv_paid_ngwee: number;
  aov_ngwee: number | null;
  payments_reconciled: boolean;
  payment_mismatch_days: string[];
};

export type OverviewData = {
  range: DateRange;
  previous_range: DateRange;
  data_through: string | null;
  min_sample_n: number;
  behaviour: Behaviour;
  previous_behaviour: Behaviour;
  commercial: Commercial;
  previous_commercial: Commercial;
  daily: Array<{
    day: string;
    sessions: number | null;
    orders_paid: number;
    gmv_paid_ngwee: number;
  }>;
};

export type SearchTerm = { normalized_term: string; searches: number; zero_results: number };

export type SearchDemandData = {
  range: DateRange;
  data_through: string | null;
  k: number;
  min_sample_n: number;
  totals: { searches: number; zero_results: number; zero_result_share_bps: number | null };
  top_terms: SearchTerm[];
  zero_result_terms: SearchTerm[];
  other: { terms: number; searches: number; zero_results: number };
};

export type FunnelStep =
  | "sessions"
  | "search_sessions"
  | "product_view_sessions"
  | "cart_adds"
  | "checkouts_started"
  | "orders_placed"
  | "orders_paid";

export type ProductsFunnelData = {
  range: DateRange;
  data_through: string | null;
  min_sample_n: number;
  funnel: Array<{ step: FunnelStep; value: number; share_of_sessions_bps: number | null }>;
  top_products: Array<{
    product_id: string;
    name: string | null;
    views: number;
    sessions: number;
  }>;
  page_views: Array<{ page_key: string; views: number }>;
  entry_pages: Array<{ page_key: string; sessions: number }>;
};

export type InsightKind = "payment_mismatch" | "rollup_failed" | "rollup_stale";

export type InsightsData = {
  range: DateRange;
  data_through: string | null;
  items: Array<{ kind: InsightKind; severity: "high" | "medium"; day: string | null }>;
  generated: "deterministic";
};

export type AnalyticsStatus = { enabled: boolean; data_through: string | null };

/** Inclusive UTC window of `days` days ending yesterday (the last fully rolled-up day). */
export function rangeEndingYesterday(days: number, now: Date = new Date()): DateRange {
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 1));
  const start = new Date(end.getTime() - (days - 1) * 86_400_000);
  return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) };
}

export function analyticsPath(api: string, range: DateRange): string {
  return `/admin/analytics/${api}?from=${range.from}&to=${range.to}`;
}

/** Basis points → fraction for percent formatting (display only; never money). */
export function bpsToFraction(bps: number): number {
  return bps / 10_000;
}

/** Relative change as a fraction, or null when there is no baseline. */
export function relativeChange(current: number, previous: number): number | null {
  if (previous <= 0) {
    return null;
  }
  return (current - previous) / previous;
}

/** Bar width (0–100) relative to the largest value in the series. */
export function barPercent(value: number, max: number): number {
  if (max <= 0 || value <= 0) {
    return 0;
  }
  return Math.max(1, Math.round((value / max) * 100));
}

/** Split seconds into whole minutes and remaining seconds for an ICU message. */
export function splitSeconds(total: number): { minutes: number; seconds: number } {
  const safe = Math.max(0, Math.floor(total));
  return { minutes: Math.floor(safe / 60), seconds: safe % 60 };
}
