import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

export type TicketTypeSales = {
  ticket_type_id: string;
  kind: string;
  name: string;
  price_ngwee: number;
  sold: number;
  checked_in: number;
  revenue_ngwee: number;
};

export type CheckInProgress = {
  issued: number;
  checked_in: number;
};

export type EscrowSplit = {
  pending_ngwee: number;
  released_ngwee: number;
};

export type OrganiserEventStats = {
  event_id: string;
  event_status: string;
  sales_by_type: TicketTypeSales[];
  revenue_ngwee: number;
  check_in: CheckInProgress;
  escrow: EscrowSplit;
  mass_refund_flagged: boolean;
};

export function createDashboardClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getEventStats(eventId: string): Promise<OrganiserEventStats> {
      return client.request<OrganiserEventStats>(`/organiser/events/${eventId}/stats`);
    },
  };
}
