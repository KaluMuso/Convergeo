"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const ordersApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type OrderSearchItem = {
  id: string;
  status: string;
  fulfilment: string;
  vendor_id: string;
  vendor_display_name: string;
  vendor_slug: string;
  customer_id: string;
  customer_phone: string | null;
  created_at: string;
};

export type OrderItem = {
  id: string;
  item_kind: string;
  qty: number;
  unit_price_ngwee: number;
  title_snapshot: string | null;
};

export type Payment = {
  id: string;
  rail: string;
  amount_ngwee: number;
  status: string;
  lenco_reference: string;
  created_at: string;
};

export type LedgerPosting = {
  id: string;
  account_id: string;
  amount_ngwee: number;
};

export type LedgerTransaction = {
  id: string;
  kind: string;
  created_at: string;
  postings: LedgerPosting[];
};

export type TimelineEvent = {
  id: string;
  actor: string | null;
  from_status: string | null;
  to_status: string | null;
  note: string | null;
  created_at: string;
};

export type OrderDetail = {
  id: string;
  status: string;
  fulfilment: string;
  cod: boolean;
  delivery_fee_ngwee: number;
  checkout_group_id: string;
  vendor_id: string;
  vendor_display_name: string;
  vendor_slug: string;
  customer_id: string;
  customer_phone: string | null;
  customer_display_name: string | null;
  created_at: string;
  items: OrderItem[];
  payments: Payment[];
  ledger: LedgerTransaction[];
  timeline: TimelineEvent[];
};

export type OrderEvent =
  | "confirm"
  | "reject"
  | "cancel"
  | "start_processing"
  | "ready_for_pickup"
  | "ship"
  | "verify_pickup"
  | "mark_delivered"
  | "confirm_received";

export const MANUAL_ESCROW_CONFIRMATION = "MANUAL ESCROW";
