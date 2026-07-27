"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const intakeApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type IntakeQueueItem = {
  session_id: string;
  status: string;
  vendor_id: string;
  vendor_display_name: string | null;
  vendor_kyc_tier: number | null;
  title: string | null;
  price_ngwee: number | null;
  listing_id: string | null;
  submitted_at: string | null;
};

export type Provenance = {
  field_name: string;
  source: string;
  confidence: number | null;
  model_ref: string | null;
};

export type IntakeMedia = {
  id: string;
  mime_type: string;
  width_px: number | null;
  height_px: number | null;
  /** Short-lived signed URL over the private quarantine bucket. */
  signed_url: string | null;
  ttl_seconds: number;
};

export type CanonicalCandidate = {
  product_id: string;
  name: string;
  score: number;
};

export type ListingDiffEntry = {
  field_name: string;
  draft_value: string | null;
  listing_value: string | null;
  changed: boolean;
};

export type IntakeDetail = {
  session_id: string;
  status: string;
  vendor_id: string;
  vendor_display_name: string | null;
  vendor_status: string | null;
  vendor_kyc_tier: number | null;
  listing_id: string | null;
  listing_status: string | null;
  draft: Record<string, unknown>;
  provenance: Provenance[];
  media: IntakeMedia[];
  warnings: string[];
  canonical_candidates: CanonicalCandidate[];
  listing_diff: ListingDiffEntry[];
  admin_notes: string | null;
};

export type IntakeActionResponse = {
  session_id: string;
  session_status: string;
  listing_id: string | null;
  listing_status: string | null;
  notification_enqueued: boolean;
  changed: boolean;
};

/**
 * Actions are per-session by design — there is deliberately no bulk variant, so
 * this union has no "approve many" member to build a batch UI from.
 */
export type IntakeAction = "approve" | "reject" | "request-changes" | "attach-canonical";

export function intakeActionPath(sessionId: string, action: IntakeAction): string {
  return `/admin/intake/${encodeURIComponent(sessionId)}/${action}`;
}
