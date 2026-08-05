"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

const API_BASE = getApiBaseUrl();

export const kycApi = createApiClient({
  baseUrl: API_BASE,
  getToken: getBrowserAccessToken,
});

export type SlaBadge = "on_track" | "due_soon" | "overdue";

export type KycQueueItem = {
  id: string;
  vendor_id: string;
  vendor_display_name: string;
  vendor_slug: string;
  tier: number;
  status: string;
  updated_at: string;
  sla_badge: SlaBadge;
  age_hours: number;
};

export type SignedDocUrl = {
  path: string;
  doc_type: "nrc" | "selfie" | "other";
  signed_url: string | null;
  expires_at: string | null;
  ttl_seconds: number;
};

export type MomoNameMatch = {
  phone: string;
  operator: string;
  resolved_name: string | null;
  legal_name: string;
  match_score: number;
  matched: boolean;
};

export type KycDetail = {
  id: string;
  vendor_id: string;
  vendor_display_name: string;
  vendor_slug: string;
  vendor_status: string;
  vendor_owner_user_id: string;
  tier: number;
  status: string;
  reviewer_notes: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  decision_reason: string | null;
  lifecycle_reason: string | null;
  momo_name_match: MomoNameMatch | null;
  documents: SignedDocUrl[];
  updated_at: string;
  sla_badge: SlaBadge;
  age_hours: number;
  docs_available: boolean;
};

export type OrphanedTierItem = {
  vendor_id: string;
  slug: string;
  display_name: string;
  vendor_status: string;
  stored_kyc_tier: number;
  vendor_updated_at: string | null;
  kyc_record_count: number;
  approved_kyc_record_count: number;
};

export type RejectReasonTemplate =
  "blurry_document" | "name_mismatch" | "expired_id" | "incomplete_submission" | "other";

export type KycDecisionResponse = {
  kyc_record_id: string;
  vendor_id: string;
  vendor_status: string;
  kyc_record_status: string;
  notification_enqueued: boolean;
};

export type VendorQueueItem = {
  vendor_id: string;
  kyc_record_id: string | null;
  display_name: string;
  slug: string;
  vendor_status: string;
  kyc_tier: number | null;
  kyc_record_status: string | null;
  tier: number | null;
  updated_at: string;
  sla_badge: SlaBadge | null;
  age_hours: number | null;
};

export type VendorKycDetail = {
  vendor_id: string;
  kyc_record_id: string;
  vendor_display_name: string;
  vendor_slug: string;
  vendor_status: string;
  tier: number;
  kyc_record_status: string;
  documents: SignedDocUrl[];
  docs_available: boolean;
  momo_name_match: MomoNameMatch | null;
  updated_at: string;
};
