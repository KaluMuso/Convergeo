import { createNotificationsApi, type NotificationsApi } from "@vergeo/ui/src/notification-center";

import { getApiBaseUrl } from "./api-base-url";

/**
 * Customer notification-center transport. Deliberately a bare `fetch` (no
 * `@vergeo/config` client) and a *dynamic* Supabase import, so the header bell
 * island adds only a few KB to first-load JS; the Supabase chunk is the same
 * lazy one every other header widget already shares.
 */
async function accessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const { getBrowserClient } = await import("@vergeo/auth/browser-client-lazy");
    const supabase = await getBrowserClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = getApiBaseUrl();
  const token = await accessToken();
  if (!base || !token) {
    throw Object.assign(new Error("unauthenticated"), { status: 401 });
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${base.replace(/\/$/, "")}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw Object.assign(new Error(`notifications ${response.status}`), {
      status: response.status,
    });
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

let api: NotificationsApi | null = null;

export function customerNotificationsApi(): NotificationsApi {
  api ??= createNotificationsApi(request, "customer", async () => (await accessToken()) !== null);
  return api;
}

export const customerNotificationsRequest = request;
