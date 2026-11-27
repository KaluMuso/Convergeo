import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { createApiClient } from "@vergeo/config";
import {
  createNotificationsApi,
  type NotificationRequest,
  type NotificationsApi,
} from "@vergeo/ui/src/notification-center";

import { getApiBaseUrl } from "./api-base-url";

/**
 * Access token for the vendor feed. Goes through the lazy Supabase accessor: importing
 * `getBrowserAccessToken` from the `@vergeo/auth` barrel put supabase-js (about 55KB gzip)
 * in the first-load JS of every page that renders the notification bell/center.
 */
async function getBrowserAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") {
    return null;
  }
  const { data } = await (await getBrowserClient()).auth.getSession();
  return data.session?.access_token ?? null;
}

/** Vendor notification-center transport (vendor audience feed). */
const client = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export const vendorNotificationsRequest: NotificationRequest = (path, init) =>
  client.request(path, { ...init, cache: "no-store" });

let api: NotificationsApi | null = null;

export function vendorNotificationsApi(): NotificationsApi {
  api ??= createNotificationsApi(
    vendorNotificationsRequest,
    "vendor",
    async () => (await getBrowserAccessToken()) !== null,
  );
  return api;
}
