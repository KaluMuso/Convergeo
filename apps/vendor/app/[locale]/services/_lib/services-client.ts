import { createApiClient } from "@vergeo/config";

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
  service_area: string | null;
  from_price_ngwee: number | null;
  status: ServiceStatus;
  portfolio_images: string[];
};

export type ServiceCreatePayload = {
  category: ServiceVertical;
  title: string;
  description?: string | null;
  service_area?: string | null;
  from_price_ngwee?: number | null;
  portfolio_images?: string[];
  status?: ServiceStatus;
};

export type ServiceUpdatePayload = Partial<ServiceCreatePayload>;

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

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
