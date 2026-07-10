"use client";

import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const disputesApi = createApiClient({
  baseUrl: API_BASE,
  getToken: () => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.sessionStorage.getItem("vergeo_admin_token");
  },
});

export type SlaBadge = "on_track" | "due_soon" | "overdue";
export type EvidenceSide = "customer" | "vendor";
export type AdminDecisionType = "full_refund" | "partial_refund" | "release";
export type QueueSort = "age" | "value";

export type DisputeQueueItem = {
  id: string;
  order_id: string;
  status: string;
  vendor_display_name: string;
  vendor_slug: string;
  customer_phone: string | null;
  order_total_ngwee: number;
  created_at: string;
  updated_at: string;
  sla_badge: SlaBadge;
  age_hours: number;
};

export type SignedEvidenceUrl = {
  path: string;
  side: EvidenceSide;
  signed_url: string | null;
  expires_at: string | null;
  ttl_seconds: number;
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

export type OrderContext = {
  id: string;
  status: string;
  fulfilment: string;
  delivery_fee_ngwee: number;
  order_total_ngwee: number;
  vendor_display_name: string;
  vendor_slug: string;
  customer_phone: string | null;
  customer_display_name: string | null;
  items: OrderItem[];
  payments: Payment[];
  ledger: LedgerTransaction[];
};

export type DisputeDetail = {
  id: string;
  order_id: string;
  status: string;
  opener_user_id: string;
  vendor_response: string | null;
  admin_decision: string | null;
  created_at: string;
  updated_at: string;
  sla_badge: SlaBadge;
  age_hours: number;
  evidence: SignedEvidenceUrl[];
  evidence_available: boolean;
  order: OrderContext;
  decidable: boolean;
};

export type DecideDisputeResponse = {
  dispute_id: string;
  order_id: string;
  status: string;
  decision: AdminDecisionType;
  admin_decision: string;
};
