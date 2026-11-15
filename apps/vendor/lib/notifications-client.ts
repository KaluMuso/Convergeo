import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";
import {
  createNotificationsApi,
  type NotificationRequest,
  type NotificationsApi,
} from "@vergeo/ui/src/notification-center";

import { getApiBaseUrl } from "./api-base-url";

/** Vendor notification-center transport (vendor audience feed). */
const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken: getBrowserAccessToken });

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
