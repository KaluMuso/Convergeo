"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const eventsApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type HighValueQueueItem = {
  event_id: string;
  title: string;
  status: string;
  organiser_vendor_id: string | null;
  projected_gmv_ngwee: number;
};

export type HighValueQueueResponse = {
  items: HighValueQueueItem[];
  threshold_ngwee: number;
};

export function listHighValueQueue(): Promise<HighValueQueueResponse> {
  return eventsApi.request<HighValueQueueResponse>("/admin/events/high-value-queue");
}

export function verifyHighValueEvent(eventId: string): Promise<{ event_id: string }> {
  return eventsApi.request<{ event_id: string }>(`/admin/events/${eventId}/high-value-verify`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export type AdvanceDebtStatus = "open" | "settled" | "written_off";

export type AdvanceDebt = {
  id: string;
  vendor_id: string;
  vendor_name: string;
  event_id: string;
  event_title: string;
  order_id: string;
  amount_ngwee: number;
  recovered_ngwee: number;
  outstanding_ngwee: number;
  status: AdvanceDebtStatus;
  due_at: string;
  suspended_at: string | null;
  blacklisted_at: string | null;
  legal_followup_at: string | null;
  created_at: string;
};

export type AdvanceDebtFilters = {
  status?: AdvanceDebtStatus | "";
  vendorId?: string;
};

export function advanceDebtsPath(filters: AdvanceDebtFilters): string {
  const params = new URLSearchParams();
  if (filters.status) {
    params.set("status", filters.status);
  }
  const vendorId = filters.vendorId?.trim();
  if (vendorId) {
    params.set("vendor_id", vendorId);
  }
  const query = params.toString();
  return query ? `/admin/event-advance-debts?${query}` : "/admin/event-advance-debts";
}

export function listAdvanceDebts(filters: AdvanceDebtFilters): Promise<{ items: AdvanceDebt[] }> {
  return eventsApi.request<{ items: AdvanceDebt[] }>(advanceDebtsPath(filters));
}

export type RepaymentInput = {
  vendor_id: string;
  amount_ngwee: number;
  reference: string;
};

export function recordAdvanceRepayment(
  input: RepaymentInput,
): Promise<{ transaction_id: string; receivable_ngwee: number }> {
  return eventsApi.request<{
    transaction_id: string;
    receivable_ngwee: number;
  }>("/admin/event-advance-debts/repayments", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
