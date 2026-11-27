import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type ServiceVertical =
  | "beauty"
  | "food-catering"
  | "auto"
  | "printing-creative"
  | "home-services"
  | "tech-services"
  | "cleaning"
  | "tailoring"
  | "lodging"
  | "property"
  | "fitness"
  | "rentals"
  | "family-fun"
  | "staffing";

export type ServiceStatus = "draft" | "active" | "paused";

export type ServiceSummary = {
  id: string;
  slug: string;
  title: string;
  category: ServiceVertical;
  description: string | null;
  service_area: string | null;
  from_price_ngwee: number | null;
  is_free?: boolean;
  bookable: boolean;
  booking_price_ngwee: number | null;
  status: ServiceStatus;
  portfolio_images: string[];
  includes: string[];
  /** Stored override (null = derived from the vertical) and the effective archetype. */
  archetype_override?: string | null;
  archetype?: string;
  attributes?: Record<string, unknown>;
};

export type ServiceCreatePayload = {
  category: ServiceVertical;
  title: string;
  description?: string | null;
  service_area?: string | null;
  from_price_ngwee?: number | null;
  is_free?: boolean;
  bookable?: boolean;
  booking_price_ngwee?: number | null;
  portfolio_images?: string[];
  includes?: string[];
  status?: ServiceStatus;
  /** Override of the archetype derived from `category`; null = derived. */
  archetype?: string | null;
  attributes?: Record<string, unknown>;
};

export type ServiceUpdatePayload = Partial<ServiceCreatePayload>;

export function createServicesClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listServices(): Promise<{ items: ServiceSummary[] }> {
      return client.request<{ items: ServiceSummary[] }>("/vendor/services");
    },

    createService(payload: ServiceCreatePayload): Promise<{ service: ServiceSummary }> {
      return client.request<{ service: ServiceSummary }>("/vendor/services", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    updateService(
      serviceId: string,
      payload: ServiceUpdatePayload,
    ): Promise<{ service: ServiceSummary }> {
      return client.request<{ service: ServiceSummary }>(`/vendor/services/${serviceId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },
  };
}

export const SERVICE_VERTICALS: ServiceVertical[] = [
  "lodging",
  "property",
  "beauty",
  "fitness",
  "cleaning",
  "home-services",
  "rentals",
  "family-fun",
  "auto",
  "tailoring",
  "food-catering",
  "printing-creative",
  "tech-services",
  "staffing",
];
