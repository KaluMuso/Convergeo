import { createApiClient } from "@vergeo/config";

export type EventCategory =
  | "workshops"
  | "comedy-theatre"
  | "pop-up-dinners"
  | "cultural-arts"
  | "lifestyle-community"
  | "free-rsvp";

export type EventStatus = "draft" | "published" | "cancelled" | "completed";

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
  ends_at?: string | null;
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
  images: string[];
  instances: EventInstanceInput[];
};

export type EventUpdatePayload = Partial<EventCreatePayload>;

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

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
