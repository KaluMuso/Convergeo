"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const claimsApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export const CLAIM_FILTERS = ["claimed", "approved", "rejected"] as const;
export type ClaimStatus = (typeof CLAIM_FILTERS)[number];
export type ClaimDecision = "approve" | "reject";

export type AdminClaim = {
  listing_id: string;
  vendor_id: string;
  vendor_name: string | null;
  title: string;
  status: ClaimStatus;
  reference: string | null;
  claimed_at: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
};

/** Decisions an admin may take from a status (mirror of the API: approved can be revoked). */
export function decisionsFor(status: ClaimStatus): ClaimDecision[] {
  if (status === "claimed") return ["approve", "reject"];
  if (status === "approved") return ["reject"];
  return [];
}

export function decisionBody(decision: ClaimDecision, note: string): Record<string, unknown> {
  const trimmed = note.trim();
  return trimmed ? { decision, note: trimmed } : { decision };
}
