"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

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
