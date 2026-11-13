import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";
import {
  createNotificationsApi,
  type NotificationRequest,
  type NotificationsApi,
} from "@vergeo/ui/src/notification-center";

import { getApiBaseUrl } from "./api-base-url";

/** Admin notification-center transport: admin-audience rows fanned out per admin user. */
const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken: getBrowserAccessToken });

const request: NotificationRequest = (path, init) =>
  client.request(path, { ...init, cache: "no-store" });

let api: NotificationsApi | null = null;

export function adminNotificationsApi(): NotificationsApi {
  api ??= createNotificationsApi(
    request,
    "admin",
    async () => (await getBrowserAccessToken()) !== null,
  );
  return api;
}
