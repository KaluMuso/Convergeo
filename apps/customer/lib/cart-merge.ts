import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "./api-base-url";

/** Merge the signed HttpOnly guest cart into the authenticated Customer cart. */
export async function mergeGuestCartIntoAccount(accessToken: string): Promise<void> {
  const client = createApiClient({
    baseUrl: getApiBaseUrl(),
    getToken: () => accessToken,
  });

  await client.request("/cart/merge", {
    method: "POST",
    credentials: "include",
  });
}
