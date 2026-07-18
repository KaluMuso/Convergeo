/**
 * M12-P02 KYC endpoint contract (as-built backend — reconciled in M12-P02b).
 *
 * GET   /kyc/status    → KycStatusResponse (application_status + flat doc_storage_paths[])
 * POST  /kyc/submit    → draft → submitted (body: KycSubmitPayload)
 * POST  /kyc/resubmit  → resubmit; 409 unless current status is `rejected`
 *
 * There is NO server draft endpoint — the onboarding draft persists in
 * localStorage only. Doc uploads use the private-bucket signing endpoint added
 * by M12-P02b (see _lib/storage.ts). The backend stores no business_name /
 * per-doc paths — only a flat `doc_storage_paths[]`.
 */
import { createApiClient } from "@vergeo/config";

import type { KycApplication, KycDocType, KycStatus, VendorStatus } from "./types";

export type MomoOperator = "mtn" | "airtel" | "zamtel";

/** Exact body accepted by POST /kyc/submit and /kyc/resubmit. */
export type KycSubmitPayload = {
  tier: number;
  doc_storage_paths: string[];
  momo_phone: string;
  momo_operator?: MomoOperator | null;
  legal_name: string;
  // Vendor business archetype selected at onboarding — persisted onto the vendor.
  archetype?: string | null;
};

/** Raw GET /kyc/status response (backend `KycStatusResponse`). */
type KycStatusResponse = {
  application_status: KycStatus;
  vendor_status: VendorStatus;
  kyc_tier: number | null;
  kyc_record_id: string | null;
  kyc_record_status: string | null;
  tier: number | null;
  doc_storage_paths: string[];
  momo_name_match: unknown;
  reviewer_notes: string | null;
  archetype: string | null;
  business_name: string | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

/** Map the backend status shape onto the UI-facing KycApplication. */
function mapStatusToApplication(status: KycStatusResponse): KycApplication {
  const [nrcPath = null, selfiePath = null] = status.doc_storage_paths ?? [];
  // Do NOT default missing tiers to 1 — orphaned seed tiers without
  // kyc_records must stay null so capability UI stays honest (VEND-01).
  return {
    vendor_id: status.kyc_record_id ?? "",
    vendor_status: status.vendor_status,
    kyc_tier: status.kyc_tier ?? null,
    kyc_status: status.application_status,
    tier: status.tier ?? null,
    kyc_record_id: status.kyc_record_id ?? null,
    kyc_record_status: status.kyc_record_status ?? null,
    // Persisted server-side now: business_name = vendor display name, archetype =
    // the onboarding business category (see migration 0034 + /kyc/status).
    business_name: status.business_name ?? null,
    business_category: status.archetype ?? null,
    momo_phone: null,
    nrc_path: nrcPath,
    selfie_path: selfiePath,
    rejection_reason: status.reviewer_notes,
    // Backend does not track per-doc rejection — resubmit re-collects both.
    rejected_docs: null,
    updated_at: "",
  };
}

export {
  canUseWholesaleCapabilities,
  effectiveKycTier,
  hasAuditableKycRecord,
  isAuditableApproved,
  shouldShowPreferredBadge,
} from "../../_lib/kyc-integrity";

export function createKycClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    async getApplication(): Promise<KycApplication> {
      const status = await client.request<KycStatusResponse>("/kyc/status");
      return mapStatusToApplication(status);
    },

    submit(payload: KycSubmitPayload): Promise<unknown> {
      return client.request<unknown>("/kyc/submit", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    resubmit(payload: KycSubmitPayload): Promise<unknown> {
      return client.request<unknown>("/kyc/resubmit", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
  };
}

export function isTerminalStatus(status: KycApplication["kyc_status"]): boolean {
  return status === "submitted" || status === "approved";
}

export function isResubmitStatus(status: KycApplication["kyc_status"]): boolean {
  return status === "rejected" || status === "resubmit";
}

export function docsRequiredForResubmit(rejectedDocs: KycDocType[] | null): KycDocType[] {
  if (!rejectedDocs || rejectedDocs.length === 0) {
    return ["nrc", "selfie"];
  }
  return rejectedDocs;
}

export function normalizeZmPhone(input: string): string {
  const digits = input.replace(/\D/g, "");
  if (digits.startsWith("260") && digits.length === 12) {
    return `0${digits.slice(3)}`;
  }
  if (digits.length === 9) {
    return `0${digits}`;
  }
  return digits;
}

export function isValidZmMobile(input: string): boolean {
  const normalized = normalizeZmPhone(input);
  return /^0(?:97|96|77|76|95|57)\d{7}$/.test(normalized);
}
