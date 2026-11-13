/**
 * Founder analytics dashboards: API types, tab registry and pure helpers.
 *
 * `/admin/analytics/{users,growth,revenue,vendors,services-events,performance}` return aggregates on
 * Africa/Lusaka reporting days: integer counts, money in integer ngwee, rates in integer
 * basis points. Revenue needs finance.read/finance.operate; the rest analytics.read.
 */

export type DashboardTab =
  "users" | "growth" | "revenue" | "vendors" | "servicesEvents" | "performance";
export type V2Tab = "behaviour" | "search" | "products" | "insights";
export type AnyAnalyticsTab = DashboardTab | V2Tab;

export type TabNeed = "analytics" | "finance";

export type TabEntry = {
  tab: AnyAnalyticsTab;
  href: string;
  /** API path segment under /admin/analytics. */
  api: string;
  needs: TabNeed;
  /** Shown only while analytics_v2_rollups is ON (`/admin/analytics/status`). */
  v2: boolean;
};

export const ALL_ANALYTICS_TABS: readonly TabEntry[] = [
  { tab: "users", href: "analytics", api: "users", needs: "analytics", v2: false },
  { tab: "growth", href: "analytics/growth", api: "growth", needs: "analytics", v2: false },
  { tab: "revenue", href: "analytics/revenue", api: "revenue", needs: "finance", v2: false },
  { tab: "vendors", href: "analytics/vendors", api: "vendors", needs: "analytics", v2: false },
  {
    tab: "servicesEvents",
    href: "analytics/services-events",
    api: "services-events",
    needs: "analytics",
    v2: false,
  },
  {
    tab: "performance",
    href: "analytics/performance",
    api: "performance",
    needs: "analytics",
    v2: false,
  },
  { tab: "behaviour", href: "analytics/behaviour", api: "overview", needs: "analytics", v2: true },
  { tab: "search", href: "analytics/search", api: "search-demand", needs: "analytics", v2: true },
  {
    tab: "products",
    href: "analytics/products",
    api: "products-funnel",
    needs: "analytics",
    v2: true,
  },
  { tab: "insights", href: "analytics/insights", api: "insights", needs: "analytics", v2: true },
];

export type Grants = { permissions: readonly string[]; unrestricted: boolean } | null;

export function grantsAllow(grants: Grants, need: TabNeed): boolean {
  if (!grants) {
    return false;
  }
  if (grants.unrestricted) {
    return true;
  }
  const wanted = need === "finance" ? ["finance.read", "finance.operate"] : ["analytics.read"];
  return wanted.some((permission) => grants.permissions.includes(permission));
}

/** Tabs the caller may open: by permission, and v2 tabs only while v2 is enabled. */
export function visibleTabs(grants: Grants, v2Enabled: boolean): TabEntry[] {
  return ALL_ANALYTICS_TABS.filter(
    (entry) => grantsAllow(grants, entry.needs) && (!entry.v2 || v2Enabled),
  );
}

export const PERIODS = ["today", "7d", "30d", "custom"] as const;
export type Period = (typeof PERIODS)[number];

export type PeriodSelection = { period: Period; from?: string; to?: string };

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Query string for a dashboard read or export; `null` while a custom range is incomplete. */
export function periodQuery(selection: PeriodSelection): string | null {
  if (selection.period !== "custom") {
    return `period=${selection.period}`;
  }
  const { from, to } = selection;
  if (!from || !to || !ISO_DAY.test(from) || !ISO_DAY.test(to) || from > to) {
    return null;
  }
  return `period=custom&from=${from}&to=${to}`;
}

/** Today's Africa/Lusaka calendar day (UTC+2, no DST) — the max for the date inputs. */
export function lusakaToday(now: Date = new Date()): string {
  return new Date(now.getTime() + 2 * 3_600_000).toISOString().slice(0, 10);
}

export type DateRange = { period?: string; from: string; to: string };

export type DailyRow = { day: string } & Record<string, number | string | null>;

export type UsersData = {
  range: DateRange;
  previous_range: DateRange;
  totals: { customers: number; vendors: number; active_vendors: number };
  new: { customers: number; vendors: number };
  previous_new: { customers: number; vendors: number };
  daily: Array<{ day: string; customers: number; vendors: number }>;
  activity:
    | { enabled: false }
    | {
        enabled: true;
        as_of: string;
        dau: number;
        dau_signed_in: number;
        wau: number;
        wau_signed_in: number;
        mau: number;
        mau_signed_in: number;
        daily_visitors: Array<{ day: string; visitors: number }>;
      };
  cohorts: Array<{
    cohort: string;
    size: number;
    retained: Array<number | null>;
    retained_bps: Array<number | null>;
    small_sample: boolean;
  }>;
};

export type GrowthKey =
  "customers" | "vendors" | "listings" | "checkouts_started" | "orders_placed" | "orders_paid";

export const GROWTH_KEYS: readonly GrowthKey[] = [
  "customers",
  "vendors",
  "listings",
  "checkouts_started",
  "orders_placed",
  "orders_paid",
];

export type GrowthData = {
  range: DateRange;
  previous_range: DateRange;
  totals: Record<GrowthKey, number>;
  previous_totals: Record<GrowthKey, number>;
  checkout_to_paid_bps: number | null;
  daily: Array<{ day: string } & Record<GrowthKey, number>>;
};

export type RevenueOrders = {
  placed: number;
  paid: number;
  cancelled: number;
  paid_order_value_ngwee: number;
  average_paid_order_ngwee: number | null;
  payments_reconciled: boolean;
  payment_mismatch_days: string[];
  paid_then_cancelled?: number;
};

export type PlatformRevenue = {
  commission_ngwee: number;
  delivery_ngwee: number;
  total_ngwee: number;
  processing_fees_ngwee: number;
};

export type RevenueData = {
  range: DateRange;
  previous_range: DateRange;
  orders: RevenueOrders;
  previous_orders: RevenueOrders;
  platform_revenue: PlatformRevenue;
  previous_platform_revenue: PlatformRevenue;
  take_rate_bps: number | null;
  refunds: {
    requested: number;
    completed: number;
    completed_ngwee: number;
    open: number;
    failed: number;
  };
  daily: Array<{
    day: string;
    orders_paid: number;
    paid_order_value_ngwee: number;
    commission_ngwee: number;
    delivery_ngwee: number;
  }>;
};

export const KYC_STATUSES = [
  "submitted",
  "under_review",
  "approved",
  "rejected",
  "suspended",
  "revoked",
] as const;
export const VENDOR_STATUSES = [
  "draft",
  "pending_kyc",
  "active",
  "suspended",
  "suspended_compliance",
] as const;

export type VendorsData = {
  range: DateRange;
  finance_visible: boolean;
  kyc: {
    current: Record<(typeof KYC_STATUSES)[number], number>;
    submitted: number;
    approved: number;
    rejected: number;
    avg_decision_hours: number | null;
  };
  vendors: {
    by_status: Record<(typeof VENDOR_STATUSES)[number], number>;
    total: number;
    active: number;
    new: number;
    selling: number;
  };
  ratings: { reviews: number; avg_x100: number | null };
  top: Array<{
    vendor_id: string;
    name: string;
    paid_orders: number;
    item_sales_ngwee: number | null;
    rating_count: number;
    rating_avg_x100: number | null;
  }>;
};

export type ServicesEventsData = {
  range: DateRange;
  services: {
    active_listings: number;
    jobs_posted: number;
    quotes_submitted: number;
    quotes_accepted: number;
    rfq_opened: number;
    rfq_quoted: number;
    rfq_accepted: number;
    bookings: number;
    bookings_paid: number;
  };
  events: {
    published: number;
    instances: number;
    tickets_sold: number;
    check_ins: number;
    check_in_rate_bps: number | null;
  };
  daily: Array<{
    day: string;
    jobs_posted: number;
    rfq_opened: number;
    tickets_sold: number;
    check_ins: number;
  }>;
};

export const PERFORMANCE_GRAINS = ["categories", "products", "vendors", "clips"] as const;
export type PerformanceGrain = (typeof PERFORMANCE_GRAINS)[number];
export const PERFORMANCE_RANKINGS = ["top", "bottom", "hidden_gems"] as const;
export type PerformanceRanking = (typeof PERFORMANCE_RANKINGS)[number];

/** One category / product / vendor / clip: funnel, conversion, repeat rate, money. */
export type PerformanceRow = {
  id: string;
  name: string;
  views: number;
  carts: number;
  orders: number;
  units: number;
  customers: number;
  repeat_customers: number;
  view_to_cart_bps: number | null;
  cart_to_order_bps: number | null;
  view_to_order_bps: number | null;
  repeat_rate_bps: number | null;
  /** Withheld (null) without finance.read / finance.operate. */
  item_sales_ngwee: number | null;
  contribution_ngwee: number | null;
  contribution_per_order_ngwee: number | null;
};

export type PerformanceScorecard = { entities: number } & Record<
  PerformanceRanking,
  PerformanceRow[]
>;

export type PerformanceContribution = {
  orders: number;
  items_ngwee: number;
  delivery_fee_ngwee: number;
  commission_ngwee: number;
  payment_fee_ngwee: number;
  courier_cost_ngwee: number;
  refunded_ngwee: number;
  refund_loss_ngwee: number;
  contribution_ngwee: number;
  contribution_per_order_ngwee: number | null;
  margin_bps: number | null;
  negative_orders: number;
  fee_unbooked_orders: number;
  courier_cost_unknown_orders: number;
};

export type PerformanceData = {
  range: DateRange;
  finance_visible: boolean;
  thresholds: {
    min_views: number;
    min_orders: number;
    clip_attribution_days: number;
    list_size: number;
  };
  funnel: {
    views: number;
    carts: number;
    orders: number;
    customers: number;
    repeat_customers: number;
    returning_customers: number;
    view_to_cart_bps: number | null;
    cart_to_order_bps: number | null;
    view_to_order_bps: number | null;
    repeat_rate_bps: number | null;
    returning_rate_bps: number | null;
  };
  contribution: PerformanceContribution | null;
} & Record<PerformanceGrain, PerformanceScorecard>;

/** True when every numeric value in every row is zero (honest "no activity" state). */
export function allZero(rows: ReadonlyArray<Record<string, unknown>>): boolean {
  return rows.every((row) => Object.entries(row).every(([key, value]) => key === "day" || !value));
}

/** A rating average stored ×100 as a one-decimal string ("4.5"). */
export function ratingText(x100: number): string {
  return (Math.round(x100 / 10) / 10).toFixed(1);
}

export function exportFilename(api: string, range: DateRange): string {
  return `vergeo5-${api}-${range.from}-${range.to}.csv`;
}
