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

export type SalesVelocity = {
  sold_last_24h: number;
  revenue_last_24h_ngwee: number;
  projected_sold: number | null;
};

export type AcquisitionSource = {
  source: string;
  orders: number;
  revenue_ngwee: number;
};

export type OrganiserEventStats = {
  event_id: string;
  event_status: string;
  sales_by_type: TicketTypeSales[];
  revenue_ngwee: number;
  check_in: CheckInProgress;
  escrow: EscrowSplit;
  mass_refund_flagged: boolean;
  velocity?: SalesVelocity;
  acquisition?: AcquisitionSource[];
};

export type TeamMember = {
  id: string;
  user_id: string;
  role: "owner" | "manager" | "door";
  accepted_at: string | null;
};

export type TeamInvite = {
  id: string;
  role: "manager" | "door";
  invitee_phone: string;
  status: string;
  expires_at: string;
};

export type TeamList = {
  members: TeamMember[];
  invites: TeamInvite[];
};

export type TeamAddResult = {
  member: TeamMember | null;
  invite: TeamInvite | null;
  invite_token: string | null;
};

export type Promo = {
  id: string;
  code: string;
  discount_kind: "percent" | "fixed";
  discount_value: number;
  max_redemptions: number | null;
  active: boolean;
};

export type Affiliate = {
  id: string;
  code: string;
  commission_bps: number;
  active: boolean;
};

export function createDashboardClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  const eventPath = (eventId: string) => `/organiser/events/${eventId}`;

  return {
    getEventStats(eventId: string): Promise<OrganiserEventStats> {
      return client.request<OrganiserEventStats>(`${eventPath(eventId)}/stats`);
    },
    getTeam(eventId: string): Promise<TeamList> {
      return client.request<TeamList>(`${eventPath(eventId)}/team`);
    },
    addTeamMember(
      eventId: string,
      body: { role: "manager" | "door"; phone: string },
    ): Promise<TeamAddResult> {
      return client.request<TeamAddResult>(`${eventPath(eventId)}/team`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    revokeTeamMember(eventId: string, memberId: string): Promise<{ status: string }> {
      return client.request<{ status: string }>(`${eventPath(eventId)}/team/${memberId}`, {
        method: "DELETE",
      });
    },
    getPromos(eventId: string): Promise<{ items: Promo[] }> {
      return client.request<{ items: Promo[] }>(`${eventPath(eventId)}/promos`);
    },
    createPromo(
      eventId: string,
      body: { code: string; discount_kind: "percent" | "fixed"; discount_value: number },
    ): Promise<Promo> {
      return client.request<Promo>(`${eventPath(eventId)}/promos`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    getAffiliates(eventId: string): Promise<{ items: Affiliate[] }> {
      return client.request<{ items: Affiliate[] }>(`${eventPath(eventId)}/affiliates`);
    },
    createAffiliate(eventId: string, body: { code: string }): Promise<Affiliate> {
      return client.request<Affiliate>(`${eventPath(eventId)}/affiliates`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  };
}
