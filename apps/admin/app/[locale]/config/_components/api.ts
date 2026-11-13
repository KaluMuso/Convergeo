"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const configApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type CommissionRate = {
  category_key: string;
  rate_bps: number;
};

export type DeliveryZone = {
  zone_key: string;
  label: string;
  fee_ngwee: number;
  active: boolean;
};

export type PlatformConfigEntry = {
  key: string;
  value: number;
  description?: string | null;
};

export type FeatureFlag = {
  flag: string;
  enabled: boolean;
  description?: string | null;
};

export type CategoryNode = {
  id: string;
  parent_id: string | null;
  name: string;
  slug: string;
  path: string;
  commission_key: string;
  prohibited: boolean;
  position: number;
};

export type TimeBand = {
  key: string;
  start: string;
  end: string;
  multiplier_bps: number;
};

/** Area-pair price formula: integer ngwee / metres / basis points only. */
export type AreaPricingSettings = {
  base_per_km_ngwee: number;
  stop_fee_ngwee: number;
  intra_area_metres: number;
  min_fee_ngwee: number;
  max_fee_ngwee: number;
  rain_multiplier_bps: number;
  zone_bounds: boolean;
  quote_ttl_minutes: number;
  time_bands: TimeBand[];
};

export type AdminArea = {
  slug: string;
  name: string;
  zone_key: string;
  active: boolean;
};

export type AreaDistance = {
  from_area: string;
  to_area: string;
  /** Decimal string (e.g. "3.15"), never a float. */
  road_km: string;
  minutes: number;
  source: string;
  manual_override: boolean;
};
