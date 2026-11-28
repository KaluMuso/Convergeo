"use client";

import { ApiError, createApiClient } from "@vergeo/config";

import { getBrowserAccessToken } from "../../../../lib/access-token";
import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const branchesApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type BranchQueueItem = {
  id: string;
  business_id: string | null;
  business_name: string | null;
  slug: string;
  display_name: string;
  branch_kind: "physical" | "online";
  branch_status: string;
  open_flags: number;
  evidence_count: number;
  submitted_at: string | null;
};

export type BranchFlag = {
  id: string;
  vendor_id: string;
  vendor_name: string | null;
  kind: string;
  matched_vendor_id: string | null;
  matched_vendor_name: string | null;
  score: number;
  details: Record<string, unknown>;
  status: "open" | "cleared" | "confirmed";
  resolution_note: string | null;
  created_at: string | null;
};

export type BranchDetail = {
  id: string;
  slug: string;
  display_name: string;
  status: string;
  branch_status: string;
  branch_kind: "physical" | "online";
  business: {
    id: string;
    legal_name: string;
    registration_type: string;
    pacra_number: string | null;
    pacra_verified_at: string | null;
    pacra_cert_url?: string | null;
  } | null;
  owner_kyc_approved: boolean;
  contact_phone: string | null;
  contact_email: string | null;
  payout_msisdn_masked: string | null;
  payout_rail: string | null;
  payout_on_hold: boolean;
  location: {
    lat: number;
    lng: number;
    landmark: string;
    address: string | null;
    map_url: string | null;
  } | null;
  plan: {
    plan_key: string;
    branch_billing_role: string;
    addon_price_ngwee: number | null;
  } | null;
  evidence: Array<{
    kind: string;
    proof_type: string | null;
    signed_url: string | null;
    content_sha256: string | null;
  }>;
  flags: BranchFlag[];
  siblings: Array<{
    id: string;
    slug: string;
    display_name: string;
    branch_status: string;
    is_primary: boolean;
  }>;
  history: Array<{
    from_status: string | null;
    to_status: string;
    note: string | null;
    created_at: string | null;
  }>;
};

export type Decision = "approve" | "request-info" | "reject";

/** Admin copy key for a failed decision (known API keys only). */
export function decisionErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    const key = error.details?.message_key;
    if (typeof key === "string" && key.startsWith("admin.branches.errors.")) {
      return key.slice("admin.".length);
    }
    if (typeof key === "string" && key.startsWith("vendor.branches.errors.")) {
      return "branches.errors.invalidTransition";
    }
    if (error.status === 403) return "branches.errors.permission";
  }
  return "branches.errors.saveFailed";
}

/** Only https Storage links are rendered as evidence images/links. */
export function safeEvidenceUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** Google Maps link for a branch location (no API key, opens in the browser). */
export function mapsUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps?q=${lat.toFixed(6)},${lng.toFixed(6)}`;
}
