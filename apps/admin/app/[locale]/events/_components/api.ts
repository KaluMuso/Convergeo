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
