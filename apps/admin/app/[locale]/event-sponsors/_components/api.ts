"use client";

import { createApiClient } from "@vergeo/config";

import { getBrowserAccessToken } from "../../../../lib/access-token";
import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const eventSponsorsApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type SponsorView = {
  index: number;
  name: string;
  logo: string | null;
  link_url: string | null;
  tagline: string | null;
  status: string;
};

export type SponsorQueueItem = {
  event_id: string;
  title: string;
  slug: string;
  event_status: string;
  organiser_name: string | null;
  sponsors: SponsorView[];
};

export type SponsorQueueResponse = {
  items: SponsorQueueItem[];
};

export type SponsorReviewBody = {
  index: number;
  name: string;
  decision: "approved" | "rejected";
  note?: string | null;
};

export async function listEventSponsorQueue(): Promise<SponsorQueueResponse> {
  return eventSponsorsApi.request<SponsorQueueResponse>("/admin/event-sponsors");
}

export async function reviewEventSponsor(eventId: string, body: SponsorReviewBody): Promise<void> {
  await eventSponsorsApi.request(`/admin/event-sponsors/${eventId}/review`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
