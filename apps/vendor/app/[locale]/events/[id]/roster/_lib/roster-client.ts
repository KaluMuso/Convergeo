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

    async downloadRosterCsv(eventId: string): Promise<Blob> {
      // Raw fetch: the CSV is a file download, not JSON, so it bypasses the shared
      // JSON client but reuses the same bearer token.
      const baseUrl = getApiBaseUrl().replace(/\/$/, "");
      const token = await getToken();
      const response = await fetch(`${baseUrl}/organiser/events/${eventId}/roster.csv`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error("roster_csv_download_failed");
      }
      return response.blob();
    },
  };
}
