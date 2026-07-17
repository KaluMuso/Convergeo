"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

const api = createApiClient({ baseUrl: API_BASE, getToken: getBrowserAccessToken });

export type Override = {
  locale: string;
  namespace: string;
  message_key: string;
  value: string;
  updated_at: string | null;
};

/** Composite map key for one override; the parts never contain "::". */
export function overrideKey(locale: string, namespace: string, messageKey: string): string {
  return [locale, namespace, messageKey].join("::");
}

export async function listOverrides(): Promise<Map<string, string>> {
  const { overrides } = await api.request<{ overrides: Override[] }>(
    "/admin/translations/overrides",
  );
  const map = new Map<string, string>();
  for (const item of overrides) {
    map.set(overrideKey(item.locale, item.namespace, item.message_key), item.value);
  }
  return map;
}

export function upsertOverride(input: {
  locale: string;
  namespace: string;
  message_key: string;
  value: string;
}): Promise<Override> {
  return api.request<Override>("/admin/translations/overrides", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function deleteOverride(input: {
  locale: string;
  namespace: string;
  message_key: string;
}): Promise<void> {
  const query = new URLSearchParams(input).toString();
  return api.request<void>(`/admin/translations/overrides?${query}`, { method: "DELETE" });
}
