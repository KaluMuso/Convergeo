"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const merchApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type MerchDraftState = {
  variant_key?: string | null;
  payload?: Record<string, unknown> | null;
  schedule_from?: string | null;
  schedule_to?: string | null;
  position?: number | null;
  active?: boolean | null;
};

export type MerchSlot = {
  id: string;
  slot_key: string;
  variant_key: string;
  payload: Record<string, unknown>;
  schedule_from: string | null;
  schedule_to: string | null;
  position: number;
  active: boolean;
  created_at: string;
  updated_at: string;
  has_draft: boolean;
  draft: MerchDraftState | null;
};

export type HeroVariant = {
  variant_key: string;
  label: string;
};

export type PreviewUrl = {
  token: string;
  customer_path: string;
  api_path: string;
};

export const SLOT_ORDER = [
  "hero",
  "banner_row",
  "flash_deal",
  "events_row",
  "featured_collections",
  "category_grid",
] as const;

export type SlotKey = (typeof SLOT_ORDER)[number];
