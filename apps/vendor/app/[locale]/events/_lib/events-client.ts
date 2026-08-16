import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type EventCategory = string;

export type EventStatus = "draft" | "published" | "cancelled" | "completed";
export type EventType = "standard" | "single" | "multi_day" | "recurring" | "free_rsvp" | "private";
export type EventVisibility = "public" | "unlisted" | "private";
export type PlatformFeePayer = "organiser" | "buyer";

export type EventInstance = {
  id: string;
  starts_at: string;
  ends_at: string | null;
  capacity: number;
  tickets_sold: number;
};

export type EventSummary = {
  id: string;
  title: string;
  slug: string;
  status: EventStatus;
  category: EventCategory | null;
  event_type: EventType;
  visibility: EventVisibility;
  recurrence_rule: string | null;
  recurrence_timezone: string | null;
  recurrence_until: string | null;
  platform_fee_payer: PlatformFeePayer;
  venue: string | null;
  landmark: string | null;
  images: string[];
  next_starts_at: string | null;
  instance_count: number;
  tickets_sold: number;
};

export type EventDetail = {
  id: string;
  title: string;
  slug: string;
  status: EventStatus;
  category: EventCategory | null;
  event_type: EventType;
  visibility: EventVisibility;
  has_access_code: boolean;
  recurrence_rule: string | null;
  recurrence_timezone: string | null;
  recurrence_until: string | null;
  recurrence_horizon_days: number;
  platform_fee_payer: PlatformFeePayer;
  city: string | null;
  id_check_enabled: boolean;
  description: string | null;
  venue: string | null;
  lat: number | null;
  lng: number | null;
  landmark: string | null;
  images: string[];
  instances: EventInstance[];
  tickets_sold: number;
};

export type EventInstanceInput = {
  id?: string;
  starts_at: string;
  ends_at: string;
  capacity: number;
};

export type EventCreatePayload = {
  title: string;
  category: EventCategory;
  description?: string | null;
  venue?: string | null;
  lat?: number | null;
  lng?: number | null;
  landmark?: string | null;
  event_type?: EventType;
  visibility?: EventVisibility;
  access_code?: string;
  recurrence_rule?: string | null;
  recurrence_timezone?: string | null;
  recurrence_until?: string | null;
  recurrence_horizon_days?: number;
  platform_fee_payer?: PlatformFeePayer;
  city?: string | null;
  id_check_enabled?: boolean;
  images: string[];
  instances: EventInstanceInput[];
};

export type EventUpdatePayload = Partial<EventCreatePayload>;

export function createEventsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listEvents(): Promise<{ items: EventSummary[] }> {
      return client.request<{ items: EventSummary[] }>("/organiser/events");
    },

    getEvent(eventId: string): Promise<{ event: EventDetail }> {
      return client.request<{ event: EventDetail }>(`/organiser/events/${eventId}`);
    },

    createEvent(payload: EventCreatePayload): Promise<{ event: EventDetail }> {
      return client.request<{ event: EventDetail }>("/organiser/events", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    updateEvent(eventId: string, payload: EventUpdatePayload): Promise<{ event: EventDetail }> {
      return client.request<{ event: EventDetail }>(`/organiser/events/${eventId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },

    publishEvent(eventId: string): Promise<{ event: EventDetail }> {
      return client.request<{ event: EventDetail }>(`/organiser/events/${eventId}/publish`, {
        method: "POST",
      });
    },

    cancelEvent(eventId: string): Promise<{ event: EventDetail }> {
      return client.request<{ event: EventDetail }>(`/organiser/events/${eventId}/cancel`, {
        method: "POST",
      });
    },

    endEvent(eventId: string): Promise<{ event: EventDetail }> {
      return client.request<{ event: EventDetail }>(`/organiser/events/${eventId}/end`, {
        method: "POST",
      });
    },
  };
}
