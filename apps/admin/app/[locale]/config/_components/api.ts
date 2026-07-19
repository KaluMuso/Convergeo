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
