/**
 * Listing/service RFQ API client — formal quotes with ngwee payload.
 */

import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "./api-base-url";

export const RFQ_DETAILS_MAX_CHARS = 4000;

export type RfqThread = {
  id: string;
  customer_id: string;
  vendor_id: string;
  listing_id: string | null;
  service_id: string | null;
  requested_details: string;
  status: string;
  quote_price_ngwee: number | null;
  quote_valid_until: string | null;
  quoted_at: string | null;
  last_message_at: string | null;
  created_at: string;
};

export type RfqMessage = {
  id: string;
  thread_id: string;
  sender_role: string;
  body: string;
  created_at: string;
};

export type CreateRfqResponse = {
  thread: RfqThread;
  message: RfqMessage;
  reused_existing_thread: boolean;
};

export type CreateRfqPayload = {
  listing_id?: string;
  service_id?: string;
  requested_details: string;
};

export function createRfqApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    createRfq(payload: CreateRfqPayload) {
      return client.request<CreateRfqResponse>("/rfq", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    listThreads(party: "customer" | "vendor" = "customer", limit = 20, offset = 0) {
      const params = new URLSearchParams({
        party,
        limit: String(limit),
        offset: String(offset),
      });
      return client.request<{ items: RfqThread[]; limit: number; offset: number }>(
        `/rfq?${params.toString()}`,
      );
    },
    getThread(threadId: string) {
      return client.request<RfqThread>(`/rfq/${threadId}`);
    },
    acceptQuoteIntoCart(rfqId: string, qty = 1) {
      return client.request("/cart/rfq/" + encodeURIComponent(rfqId) + "/accept", {
        method: "POST",
        body: JSON.stringify({ qty }),
      });
    },
  };
}

export type RfqApiClient = ReturnType<typeof createRfqApiClient>;
