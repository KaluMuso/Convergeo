/**
 * Runtime capability probe for listing-anchored enquiries (CAN-SOC-001 / BLK-202).
 *
 * The PDP must not render a Contact Vendor CTA unless the deployed FastAPI
 * exposes `/enquiries`. Production can lag Git on both API deploy and migration
 * 0082; an anonymous GET probe fails closed on 404/5xx and treats auth-required
 * responses (401/403) as proof the router is registered.
 */

import { absoluteApiUrl, type resolveApiBaseUrl } from "./api-base-url";

type EnvBag = Parameters<typeof resolveApiBaseUrl>[0];

/** Interpret an anonymous probe of `GET /enquiries` — exported for unit tests. */
export function isEnquiriesEndpointAvailable(status: number): boolean {
  if (status === 404) {
    return false;
  }
  if (status >= 500) {
    return false;
  }
  // Router registered: guests are refused (401/403) before any DB work on POST.
  return status === 401 || status === 403 || status === 200;
}

/**
 * Server-only: returns true only when the configured API origin exposes enquiries.
 * Fails closed on missing base URL, network errors, 404, and 5xx.
 */
export async function contactVendorCapabilityAvailable(
  env: EnvBag = process.env,
): Promise<boolean> {
  const url = absoluteApiUrl("/enquiries", env);
  if (!url) {
    return false;
  }

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    return isEnquiriesEndpointAvailable(response.status);
  } catch {
    return false;
  }
}
