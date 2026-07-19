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

export type VendorAnalytics = {
  window: number;
  days: string[];
  sales_ngwee_by_day: number[];
  orders_by_day: number[];
  views_by_day: number[];
  top_listings: TopListing[];
  conversion_hint: ConversionHint;
};

export function createAnalyticsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    get(window: AnalyticsWindow): Promise<VendorAnalytics> {
      return client.request<VendorAnalytics>(`/vendor/analytics?window=${window}`);
    },
  };
}
