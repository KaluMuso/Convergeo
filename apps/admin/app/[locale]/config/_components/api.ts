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

export type FxRate = {
  id: string;
  rate_zmw_per_usd_micros: number;
  vendor_margin_bps: number;
  source: string;
  source_reference: string | null;
  effective_at: string;
  expires_at: string;
  stale: boolean;
};

export type FxRatesResponse = {
  current: FxRate | null;
  history: FxRate[];
};

export type CategoryPolicy = {
  category_id: string;
  category_name: string;
  path: string;
  phase: number;
  enabled: boolean;
  allowed_product_classes: string[];
  minimum_kyc_tier: number | null;
  required_licence_types: string[];
  evidence_requirements: Record<string, unknown>;
  high_risk: boolean;
};

export type ClassDReadiness = {
  customer_release: boolean;
  operations_approved: boolean;
  escrow_hours: number;
  shopper_visible: boolean;
};

export type VendorGovernanceItem = {
  vendor_id: string;
  display_name: string | null;
  slug: string | null;
  status: string;
  total_orders: number;
  cancelled_orders: number;
  cancel_rate: number;
  severity: "ok" | "warn" | "critical";
};

export type VendorGovernanceResponse = {
  severity_filter: string;
  warn_threshold: number;
  critical_threshold: number;
  min_orders: number;
  generated_at: string;
  vendors: VendorGovernanceItem[];
};
