import { createApiClient } from "@vergeo/config";

export type TicketKind = "fixed" | "tier" | "free_rsvp";

export type TicketTypeSummary = {
  id: string;
  event_id: string;
  kind: TicketKind;
  name: string;
  price_ngwee: number;
  qty_cap: number | null;
  per_customer_cap: number | null;
  tickets_sold: number;
};

export type TicketTypeCreatePayload = {
  kind: TicketKind;
  name: string;
  price_ngwee: number;
  qty_cap?: number | null;
  per_customer_cap?: number | null;
};

export type TicketTypeUpdatePayload = Partial<TicketTypeCreatePayload>;

export type AllocationRow = {
  instance_id: string;
  starts_at: string;
  allocation: number | null;
  sold: number;
};

export type AllocationInput = {
  instance_id: string;
  allocation: number;
};

export type PriceTierRow = {
  min_qty: number;
  price_ngwee: number;
};

export type PricingConfig = {
  ticket_type_id: string;
  base_price_ngwee: number;
  early_bird_price_ngwee: number | null;
  early_bird_until: string | null;
  tiers: PriceTierRow[];
};

export type EarlyBirdInput = {
  early_bird_price_ngwee: number | null;
  early_bird_until: string | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createTicketsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listTicketTypes(eventId: string): Promise<TicketTypeSummary[]> {
      return client.request<TicketTypeSummary[]>(`/organiser/events/${eventId}/ticket-types`);
    },

    createTicketType(
      eventId: string,
      payload: TicketTypeCreatePayload,
    ): Promise<TicketTypeSummary> {
      return client.request<TicketTypeSummary>(`/organiser/events/${eventId}/ticket-types`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    updateTicketType(
      ticketTypeId: string,
      payload: TicketTypeUpdatePayload,
    ): Promise<TicketTypeSummary> {
      return client.request<TicketTypeSummary>(`/organiser/ticket-types/${ticketTypeId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },

    deleteTicketType(ticketTypeId: string): Promise<void> {
      return client.request<void>(`/organiser/ticket-types/${ticketTypeId}`, {
        method: "DELETE",
      });
    },

    getAllocations(ticketTypeId: string): Promise<AllocationRow[]> {
      return client.request<AllocationRow[]>(`/organiser/ticket-types/${ticketTypeId}/allocations`);
    },

    setAllocations(ticketTypeId: string, allocations: AllocationInput[]): Promise<AllocationRow[]> {
      return client.request<AllocationRow[]>(
        `/organiser/ticket-types/${ticketTypeId}/allocations`,
        {
          method: "PUT",
          body: JSON.stringify({ allocations }),
        },
      );
    },

    getPricing(ticketTypeId: string): Promise<PricingConfig> {
      return client.request<PricingConfig>(`/organiser/ticket-types/${ticketTypeId}/pricing`);
    },

    setEarlyBird(ticketTypeId: string, input: EarlyBirdInput): Promise<PricingConfig> {
      return client.request<PricingConfig>(`/organiser/ticket-types/${ticketTypeId}/early-bird`, {
        method: "PUT",
        body: JSON.stringify(input),
      });
    },

    setPriceTiers(ticketTypeId: string, tiers: PriceTierRow[]): Promise<PricingConfig> {
      return client.request<PricingConfig>(`/organiser/ticket-types/${ticketTypeId}/price-tiers`, {
        method: "PUT",
        body: JSON.stringify({ tiers }),
      });
    },
  };
}
