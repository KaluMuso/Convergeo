"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const catalogApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export const CATALOG_TABS = ["listings", "services", "events", "vendors"] as const;
export type CatalogTab = (typeof CATALOG_TABS)[number];
export type CatalogAction = "hide" | "block" | "restore" | "edit";

export type CatalogHold = {
  id: string;
  action: "hide" | "block";
  from_status: string;
  reason: string;
  actor: string | null;
  created_at: string | null;
};

export type CatalogEntity = {
  kind: "listing" | "service" | "event" | "vendor";
  id: string;
  label: string;
  status: string;
  vendor_id: string | null;
  visible: boolean;
  href: string;
  hold: CatalogHold | null;
};

/** Which permission the API requires to read / mutate each tab (mirrors app.core.auth). */
export const TAB_PERMISSIONS: Record<CatalogTab, { read: string; write: string | null }> = {
  listings: { read: "products.manage", write: "products.manage" },
  services: { read: "services.read", write: null },
  events: { read: "events.manage", write: "events.manage" },
  vendors: { read: "vendors.manage", write: "vendors.manage" },
};

export function canAccessTab(
  tab: CatalogTab,
  grants: { permissions: string[]; unrestricted: boolean } | null,
  mode: "read" | "write",
): boolean {
  if (!grants) return false;
  if (grants.unrestricted) return true;
  const required = TAB_PERMISSIONS[tab][mode];
  return required !== null && grants.permissions.includes(required);
}

/**
 * Actions offered for a row. The server is authoritative (guarded SQL edges);
 * this only avoids offering buttons that would certainly be refused.
 */
export function actionsFor(tab: CatalogTab, entity: CatalogEntity): CatalogAction[] {
  const actions: CatalogAction[] = [];
  if (entity.hold) {
    actions.push("restore");
    if (entity.hold.action === "hide" && tab !== "vendors") actions.push("block");
  } else if (tab === "vendors") {
    if (entity.status === "active") actions.push("block");
    // A suspension made elsewhere (flag escalation) can be lifted here too.
    if (entity.status === "suspended") actions.push("restore");
  } else {
    const hideable =
      tab === "events"
        ? entity.status === "published"
        : entity.status === "active" || entity.status === "paused";
    if (hideable) actions.push("hide");
    if (
      entity.status !== "removed" &&
      entity.status !== "cancelled" &&
      entity.status !== "completed"
    )
      actions.push("block");
  }
  actions.push("edit");
  return actions;
}

export function isValidReason(reason: string): boolean {
  return reason.trim().length >= 3;
}

export function catalogPath(tab: CatalogTab, query: string, heldOnly: boolean): string {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (heldOnly) params.set("held_only", "true");
  const suffix = params.toString();
  return `/admin/catalog/${tab}${suffix ? `?${suffix}` : ""}`;
}
