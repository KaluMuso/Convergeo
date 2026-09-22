import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "./api-base-url";

import type { CartMergeResolution } from "./auth-transition";

/** Merge the signed HttpOnly guest cart into the authenticated Customer cart. */
export async function mergeGuestCartIntoAccount(
  accessToken: string,
  resolution?: CartMergeResolution,
): Promise<void> {
  const client = createApiClient({
    baseUrl: getApiBaseUrl(),
    getToken: () => accessToken,
  });

  await client.request("/cart/merge", {
    method: "POST",
    credentials: "include",
    ...(resolution
      ? {
          body: JSON.stringify(resolution),
          headers: { "Content-Type": "application/json" },
        }
      : {}),
  });
}
