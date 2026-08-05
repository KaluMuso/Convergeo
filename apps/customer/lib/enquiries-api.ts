/**
 * Listing-anchored enquiry API client (R02 / D37).
 * Mirrors POST /enquiries and related read endpoints on the FastAPI backend.
 */

import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "./api-base-url";

export const ENQUIRY_BODY_MAX_CHARS = 2000;

export type EnquiryThread = {
  id: string;
  subject_kind: string;
  subject_id: string;
  vendor_id: string;
  customer_id: string;
  status: string;
  last_message_at: string | null;
  created_at: string;
};

export type EnquiryMessage = {
  id: string;
  thread_id: string;
  sender_role: string;
  body: string;
  created_at: string;
};

export type CreateEnquiryResponse = {
  thread: EnquiryThread;
  message: EnquiryMessage;
  reused_existing_thread: boolean;
};

export type CreateEnquiryPayload = {
  subject_kind: "listing" | "event" | "service";
  subject_id: string;
  body: string;
};

export function createEnquiriesApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    createEnquiry(payload: CreateEnquiryPayload) {
      return client.request<CreateEnquiryResponse>("/enquiries", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    listEnquiries(limit = 20, offset = 0) {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      });
      return client.request<{ items: EnquiryThread[]; limit: number; offset: number }>(
        `/enquiries?${params.toString()}`,
      );
    },
  };
}

export type EnquiriesApiClient = ReturnType<typeof createEnquiriesApiClient>;
