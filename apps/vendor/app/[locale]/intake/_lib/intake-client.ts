import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type IntakeStatus =
  | "collecting"
  | "needs_details"
  | "ready_for_vendor_review"
  | "submitted"
  | "pending_admin_review"
  | "approved"
  | "rejected"
  | "expired";

export type FieldSource = "vendor_typed" | "rule" | "model";

export type IntakeSessionSummary = {
  id: string;
  status: IntakeStatus | string;
  title: string | null;
  price_ngwee: number | null;
  pending_request_count: number;
  listing_id: string | null;
  last_activity_at: string | null;
};

export type FieldProvenance = {
  field_name: string;
  source: FieldSource | string;
  confidence: number | null;
  model_ref: string | null;
};

export type IntakeMedia = {
  id: string;
  mime_type: string;
  width_px: number | null;
  height_px: number | null;
  /** Null when storage is unreachable — the page still renders the text fields. */
  signed_url: string | null;
  ttl_seconds: number;
};

/**
 * A follow-up recorded as data on the intake record. The WhatsApp lane is
 * inbound-only, so these are rendered here rather than sent as a message.
 */
export type PendingRequest = {
  key: string;
  field_name: string | null;
  params: Record<string, string>;
};

export type IntakeDraft = {
  title: string | null;
  category_id: string | null;
  price_ngwee: number | null;
  pricing_mode: string | null;
  quantity: number | null;
  stock_mode: string | null;
  sale_unit: string | null;
  condition: string | null;
  description: string | null;
};

export type IntakeSessionDetail = {
  id: string;
  status: IntakeStatus | string;
  draft: IntakeDraft;
  provenance: FieldProvenance[];
  media: IntakeMedia[];
  pending_requests: PendingRequest[];
  missing_fields: string[];
  submittable: boolean;
  listing_id: string | null;
};

export type DraftPatch = Partial<{
  title: string | null;
  category_id: string | null;
  price_ngwee: number | null;
  pricing_mode: string | null;
  quantity: number | null;
  stock_mode: string | null;
  sale_unit: string | null;
  condition: string | null;
  description: string | null;
}>;

export type SubmitResult = {
  session_id: string;
  listing_id: string;
  listing_status: string;
  session_status: string;
  already_submitted: boolean;
};

export function createIntakeClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listSessions(): Promise<IntakeSessionSummary[]> {
      return client.request<IntakeSessionSummary[]>("/vendor/intake/sessions");
    },

    getSession(sessionId: string): Promise<IntakeSessionDetail> {
      return client.request<IntakeSessionDetail>(
        `/vendor/intake/sessions/${encodeURIComponent(sessionId)}`,
      );
    },

    patchDraft(sessionId: string, patch: DraftPatch): Promise<IntakeSessionDetail> {
      return client.request<IntakeSessionDetail>(
        `/vendor/intake/sessions/${encodeURIComponent(sessionId)}/draft`,
        { method: "PATCH", body: JSON.stringify(patch) },
      );
    },

    submit(sessionId: string): Promise<SubmitResult> {
      return client.request<SubmitResult>(
        `/vendor/intake/sessions/${encodeURIComponent(sessionId)}/submit`,
        { method: "POST" },
      );
    },

    /**
     * Redeem a single-use review link. The link is not the authorisation: this
     * still runs as the signed-in vendor and 403s on someone else's session.
     */
    redeemLink(token: string): Promise<IntakeSessionDetail> {
      return client.request<IntakeSessionDetail>("/vendor/intake/links/redeem", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
    },
  };
}
