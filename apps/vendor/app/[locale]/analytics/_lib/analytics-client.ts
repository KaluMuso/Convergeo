import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type AnalyticsWindow = 7 | 30;

export type TopListing = {
  listing_id: string;
  title: string;
  units: number;
  revenue_ngwee: number;
};

export type ConversionHint = {
  orders_total: number;
  views_total: number;
  conversion_pct: number;
};

export type OrderActivityRatio = {
  orders_total: number;
  cart_activity_events_total: number;
  orders_per_100_cart_activity_events: number | null;
};

export type VendorAnalytics = {
  window: number;
  days: string[];
  sales_ngwee_by_day: number[];
  orders_by_day: number[];
  cart_activity_events_by_day: number[];
  order_activity_ratio: OrderActivityRatio;
  /** @deprecated Cart/checkout event rows, not listing views. */
  views_by_day: number[];
  top_listings: TopListing[];
  /** @deprecated Independent totals, not a conversion cohort. */
  conversion_hint: ConversionHint;
};

type AnalyticsPayload = Omit<
  VendorAnalytics,
  "cart_activity_events_by_day" | "order_activity_ratio"
> &
  Partial<Pick<VendorAnalytics, "cart_activity_events_by_day" | "order_activity_ratio">>;

/** Supports older APIs during rollout without inheriting their conversion label. */
export function normalizeVendorAnalytics(data: AnalyticsPayload): VendorAnalytics {
  const activity = data.cart_activity_events_by_day ?? data.views_by_day;
  const eventsTotal = activity.reduce((total, count) => total + count, 0);
  const ordersTotal = data.orders_by_day.reduce((total, count) => total + count, 0);
  return {
    ...data,
    cart_activity_events_by_day: activity,
    order_activity_ratio: data.order_activity_ratio ?? {
      orders_total: ordersTotal,
      cart_activity_events_total: eventsTotal,
      orders_per_100_cart_activity_events:
        // Preserve the server's rounding for old APIs; change the definition,
        // not the historical value. Its legacy zero is unavailable if no events.
        eventsTotal > 0 ? data.conversion_hint.conversion_pct : null,
    },
  };
}

export type VendorAnalyticsSummary = {
  window_days: number;
  total_views: number;
  total_orders: number;
  gmv_ngwee: number;
  impressions: number;
  pdp_views: number;
};

export function createAnalyticsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    async get(window: AnalyticsWindow): Promise<VendorAnalytics> {
      const data = await client.request<AnalyticsPayload>(`/vendor/analytics?window=${window}`);
      return normalizeVendorAnalytics(data);
    },
    getSummary(): Promise<VendorAnalyticsSummary> {
      return client.request<VendorAnalyticsSummary>("/vendor/analytics/summary");
    },
  };
}
