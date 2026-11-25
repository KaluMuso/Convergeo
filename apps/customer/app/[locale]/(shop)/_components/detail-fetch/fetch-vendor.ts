import { createApiClient } from "@vergeo/config";
import { absoluteApiUrl, getApiBaseUrl } from "../../../../../lib/api-base-url";
export type VendorProfilePayload = Record<string, unknown>;
export type VendorFetchResult =
  { kind: "vendor"; data: VendorProfilePayload } | { kind: "not_found" } | { kind: "unavailable" };
export async function fetchVendorProfile(slug: string): Promise<VendorFetchResult> {
  const url = absoluteApiUrl(`/directory/${encodeURIComponent(slug)}`);
  if (!url) return { kind: "unavailable" };
  try {
    const response = await fetch(url, {
      next: { revalidate: 3600, tags: [`vendor:${slug}`, "directory"] },
    });
    if (response.status === 404) return { kind: "not_found" };
    if (!response.ok) return { kind: "unavailable" };
    return { kind: "vendor", data: (await response.json()) as VendorProfilePayload };
  } catch {
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl() });
      return {
        kind: "vendor",
        data: await client.request(`/directory/${encodeURIComponent(slug)}`),
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
