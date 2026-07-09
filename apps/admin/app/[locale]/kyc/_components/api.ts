"use client";

import { createApiClient } from "@vergeo/config";

const API_BASE = process.env.NEXT_PUBLIC_VERGEO_API_URL ?? "http://localhost:8000";

export const kycApi = createApiClient({
  baseUrl: API_BASE,
  getToken: () => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.sessionStorage.getItem("vergeo_admin_token");
  },
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
  momo_name_match: MomoNameMatch | null;
  documents: SignedDocUrl[];
  updated_at: string;
  sla_badge: SlaBadge;
  age_hours: number;
  docs_available: boolean;
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
