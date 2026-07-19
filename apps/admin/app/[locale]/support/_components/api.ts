"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const supportApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type CustomerSummary = {
  id: string;
  phone: string | null;
  display_name: string | null;
  locale: string;
};

export type OrderSummary = {
  id: string;
  status: string;
  vendor_display_name: string;
  vendor_slug: string;
  created_at: string;
};

export type ContextCard = {
  customer: CustomerSummary;
  orders: OrderSummary[];
  open_orders_count: number;
  latest_order_status: string | null;
};

export type LookupResponse = {
  matches: ContextCard[];
};

export type InteractionLogEntry = {
  id: string;
  kind: "canned" | "free_text";
  channel: string | null;
  template_key: string | null;
  message_preview: string | null;
  actor: string | null;
  order_id: string | null;
  created_at: string;
  source: "outbox" | "audit_log";
};

export type SendResponse = {
  customer_id: string;
  channel: string;
  template_key: string | null;
  outbox_id: string | null;
  deduped: boolean;
};

export const CANNED_TEMPLATE_KEYS = [
  "order_status_update",
  "delivery_eta",
  "payment_reminder",
  "apology_delay",
  "pickup_ready",
] as const;

export type CannedTemplateKey = (typeof CANNED_TEMPLATE_KEYS)[number];
