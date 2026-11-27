import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

import type { OrderActionResponse, VendorActionName } from "./action-bar";

export type OrderQueueItem = {
  id: string;
  status: string;
  fulfilment: string;
  total_ngwee: number;
  item_count: number;
  preview_title: string;
  created_at: string;
  available_actions: VendorActionName[];
  urgency: number;
};

export type VendorDashboard = {
  takings_ngwee: number;
  takings_date: string;
  needs_action: OrderQueueItem[];
  queue_counts: Record<string, number>;
  archetype?: string | null;
  business_archetype?: string | null;
};

const CACHE_KEY = "vergeo5.vendor.orders.queue.v1";
type QueueCache = {
  saved_at: string;
  dashboard: VendorDashboard | null;
  queue: OrderQueueItem[] | null;
};

export function createOrdersQueueClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getDashboard(): Promise<VendorDashboard> {
      return client.request<VendorDashboard>("/vendor/orders/dashboard");
    },
    listQueue(status: string): Promise<OrderQueueItem[]> {
      const query = new URLSearchParams({ status });
      return client.request<OrderQueueItem[]>(`/vendor/orders/queue?${query.toString()}`);
    },
    confirm(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/confirm`, {
        method: "POST",
      });
    },
    pack(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/pack`, {
        method: "POST",
      });
    },
    ship(orderId: string, trackingNote: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/ship`, {
        method: "POST",
        body: JSON.stringify({ tracking_note: trackingNote }),
      });
    },
    readyForPickup(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/ready-for-pickup`, {
        method: "POST",
      });
    },
    readyForCollection(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/ready-for-collection`, {
        method: "POST",
      });
    },
  };
}

export function readQueueCache(): QueueCache | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as QueueCache;
  } catch {
    return null;
  }
}

export function writeQueueCache(payload: QueueCache): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore quota / private-mode failures.
  }
}
