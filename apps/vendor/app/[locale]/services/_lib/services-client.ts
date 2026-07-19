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
  | "tailoring";

export type ServiceStatus = "draft" | "active" | "paused";

export type ServiceSummary = {
  id: string;
  slug: string;
  title: string;
  category: ServiceVertical;
  description: string | null;
  service_area: string | null;
  from_price_ngwee: number | null;
  bookable: boolean;
  booking_price_ngwee: number | null;
  status: ServiceStatus;
  portfolio_images: string[];
  includes: string[];
};

export type ServiceCreatePayload = {
  category: ServiceVertical;
  title: string;
  description?: string | null;
  service_area?: string | null;
  from_price_ngwee?: number | null;
  bookable?: boolean;
  booking_price_ngwee?: number | null;
  portfolio_images?: string[];
  includes?: string[];
  status?: ServiceStatus;
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
  "beauty",
  "food-catering",
  "auto",
  "printing-creative",
  "home-services",
  "tech-services",
  "cleaning",
  "tailoring",
];
