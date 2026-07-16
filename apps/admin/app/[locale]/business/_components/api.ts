"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const businessApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type BusinessBuyerStatus = "pending" | "verified" | "rejected" | "suspended";

export type BusinessBuyer = {
  id: string;
  user_id: string;
  legal_name: string;
  registration_no: string;
  tpin: string | null;
  status: BusinessBuyerStatus;
  reviewer_notes: string | null;
  verified_at: string | null;
  created_at: string | null;
  notification_enqueued?: boolean;
};

export type StatusFilter = BusinessBuyerStatus | "all";

export function listBusinessBuyers(filter: StatusFilter): Promise<BusinessBuyer[]> {
  const query = filter === "all" ? "" : `?status=${filter}`;
  return businessApi.request<BusinessBuyer[]>(`/admin/business${query}`);
}

export function verifyBusinessBuyer(id: string): Promise<BusinessBuyer> {
  return businessApi.request<BusinessBuyer>(`/admin/business/${id}/verify`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function rejectBusinessBuyer(id: string, reviewerNotes: string): Promise<BusinessBuyer> {
  return businessApi.request<BusinessBuyer>(`/admin/business/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reviewer_notes: reviewerNotes }),
  });
}
