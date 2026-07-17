import { createApiClient } from "@vergeo/config";

export type RosterAttendee = {
  ticket_id: string;
  holder_name: string | null;
  ticket_type_id: string;
  ticket_type_name: string;
  kind: string;
  instance_id: string;
  starts_at: string;
  status: "issued" | "checked_in";
  checked_in_at: string | null;
};

export type OrganiserEventRoster = {
  event_id: string;
  event_status: string;
  total: number;
  checked_in: number;
  truncated: boolean;
  attendees: RosterAttendee[];
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createRosterClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getEventRoster(eventId: string): Promise<OrganiserEventRoster> {
      return client.request<OrganiserEventRoster>(`/organiser/events/${eventId}/roster`);
    },
  };
}
