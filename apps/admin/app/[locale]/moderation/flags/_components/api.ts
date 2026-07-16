"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const flagsApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type FlagStatus = "open" | "actioned" | "dismissed";
export type EntityType = "listing" | "review" | "prohibited";

export type FlagQueueItem = {
  id: string;
  entity_type: EntityType;
  entity_id: string;
  reason: string;
  reporter_user_id: string;
  status: FlagStatus;
  created_at: string;
  updated_at: string;
  vendor_id: string | null;
  vendor_display_name: string | null;
  vendor_slug: string | null;
  repeat_offender_count: number;
  entity_label: string | null;
  entity_status: string | null;
};

export type FlagActionResponse = {
  flag_id: string;
  flag_status: FlagStatus;
  entity_type: EntityType;
  entity_id: string;
  vendor_id: string | null;
  vendor_status: string | null;
  entity_status: string | null;
  notification_enqueued: boolean;
  repeat_offender_count: number;
};

export type FlagAction = "dismiss" | "unpublish" | "remove" | "warn-vendor" | "escalate-suspend";

export function flagActionPath(flagId: string, action: FlagAction): string {
  return `/admin/flags/${flagId}/${action}`;
}
