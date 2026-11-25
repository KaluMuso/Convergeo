import { createApiClient } from "@vergeo/config";

import { absoluteApiUrl, getApiBaseUrl } from "../../../../../lib/api-base-url";
export const SERVICE_REVALIDATE_SECONDS = 300;
export type ServiceDetailPayload = {
  id: string;
  slug: string;
  title: string;
  category: string;
  description: string | null;
  service_area: string | null;
  from_price_ngwee: number | null;
  is_free?: boolean;
  bookable: boolean;
  booking_price_ngwee: number | null;
  portfolio_images: string[];
  includes: string[];
  packages?: unknown;
  provider: {
    id: string;
    slug: string;
    display_name: string;
    preferred_badge: boolean;
    response_time_tier: "fast" | "same_day" | "slow" | null;
  };
};
export type ServiceFetchResult =
  { kind: "service"; data: ServiceDetailPayload } | { kind: "not_found" } | { kind: "unavailable" };
export async function fetchServiceDetail(slug: string): Promise<ServiceFetchResult> {
  const url = absoluteApiUrl(`/services/${encodeURIComponent(slug)}`);
  if (!url) return { kind: "unavailable" };
  try {
    const response = await fetch(url, {
      next: { revalidate: SERVICE_REVALIDATE_SECONDS, tags: [`service:${slug}`, "services"] },
    });
    if (response.status === 404) return { kind: "not_found" };
    if (!response.ok) return { kind: "unavailable" };
    return { kind: "service", data: (await response.json()) as ServiceDetailPayload };
  } catch {
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl() });
      return {
        kind: "service",
        data: await client.request(`/services/${encodeURIComponent(slug)}`),
      };
    } catch (error) {
      const status =
        typeof error === "object" && error && "status" in error
          ? (error as { status: number }).status
          : null;
      return status === 404 ? { kind: "not_found" } : { kind: "unavailable" };
    }
  }
}
