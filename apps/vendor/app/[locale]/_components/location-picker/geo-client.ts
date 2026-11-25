import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type GeoSearchResult = {
  label: string;
  lat: number;
  lng: number;
};

export function createGeoClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    search(query: string): Promise<GeoSearchResult[]> {
      const q = query.trim();
      return client.request<GeoSearchResult[]>(`/geo/search?q=${encodeURIComponent(q)}`);
    },
  };
}
