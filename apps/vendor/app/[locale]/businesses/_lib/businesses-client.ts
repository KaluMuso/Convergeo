import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type BranchStatus = "draft" | "pending_review" | "info_requested" | "approved" | "rejected";

export type Allowance = {
  registered: boolean;
  plan_key: string | null;
  included_shops: number | null;
  extra_shop_price_ngwee: number | null;
  used: number;
  limit: number | null;
  can_add: boolean;
  next_billing_role: "included" | "addon" | null;
  next_price_ngwee: number | null;
  blocked_reason: "unregistered" | "plan" | null;
};

export type Branch = {
  id: string;
  slug: string;
  display_name: string;
  status: string;
  branch_status: BranchStatus;
  branch_kind: "physical" | "online";
  is_primary: boolean;
  payout_on_hold: boolean;
  review_note: string | null;
};

export type Business = {
  id: string;
  legal_name: string;
  registration_type: "company" | "business_name" | "unregistered" | "unspecified";
  pacra_number: string | null;
  pacra_verified: boolean;
  status: string;
  owner_kyc_approved: boolean;
  staff_seats: number | null;
  staff_used: number;
  allowance: Allowance;
  branches: Branch[];
};

export type BusinessesResponse = { enabled: boolean; businesses: Business[] };

export type DayHours = { open?: string; close?: string; closed?: boolean };

export type BranchCreatePayload = {
  display_name: string;
  description?: string;
  branch_kind: "physical" | "online";
  location?: { lat: number; lng: number; landmark: string; address?: string; map_url?: string };
  hours: Partial<Record<"mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun", DayHours>>;
  contact_phone: string;
  contact_email?: string;
  whatsapp_msisdn?: string;
  payout_msisdn: string;
  payout_rail: "mtn" | "airtel" | "zamtel";
};

export type BranchCreated = {
  branch: Branch;
  plan_key: string | null;
  branch_billing_role: "included" | "addon";
  addon_price_ngwee: number | null;
  needs_review_flags: number;
};

export type EvidenceKind = "storefront_photo" | "premises_proof";
export type ProofType = "lease" | "utility_bill" | "council_permit";

type SignResponse = { bucket: string; path: string; token: string; signed_url: string };

const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
export const MAX_EVIDENCE_BYTES = 10_485_760;

export async function sha256Hex(file: Blob): Promise<string | null> {
  try {
    const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return null;
  }
}

export function isAllowedEvidence(file: File): boolean {
  return ALLOWED_TYPES.has(file.type) && file.size > 0 && file.size <= MAX_EVIDENCE_BYTES;
}

export function createBusinessesClient(getToken: () => string | null) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

  async function uploadSigned(file: File, signed: SignResponse): Promise<string> {
    const response = await fetch(signed.signed_url, {
      method: "PUT",
      headers: { "Content-Type": file.type, "x-upsert": "false" },
      body: file,
    });
    if (!response.ok) throw new Error("upload_failed");
    return signed.path;
  }

  return {
    list: () => client.request<BusinessesResponse>("/vendor/businesses"),
    updateBusiness: (
      businessId: string,
      body: Partial<
        Pick<Business, "legal_name" | "pacra_number"> & {
          registration_type: "company" | "business_name" | "unregistered";
          pacra_cert_path: string;
        }
      >,
    ) =>
      client.request<Business>(`/vendor/businesses/${businessId}`, {
        method: "PATCH",
        ...json(body),
      }),
    createBranch: (businessId: string, body: BranchCreatePayload) =>
      client.request<BranchCreated>(`/vendor/businesses/${businessId}/branches`, {
        method: "POST",
        ...json(body),
      }),
    async uploadPacraCertificate(businessId: string, file: File): Promise<string> {
      const signed = await client.request<SignResponse>(
        `/vendor/businesses/${businessId}/evidence/sign`,
        {
          method: "POST",
          ...json({
            kind: "pacra_certificate",
            content_type: file.type,
            file_size_bytes: file.size,
          }),
        },
      );
      return uploadSigned(file, signed);
    },
    async uploadEvidence(
      businessId: string,
      branchId: string,
      kind: EvidenceKind,
      file: File,
      proofType: ProofType | null,
    ): Promise<{ duplicate_flags: number }> {
      const signed = await client.request<SignResponse>(
        `/vendor/businesses/${businessId}/evidence/sign?branch_id=${encodeURIComponent(branchId)}`,
        { method: "POST", ...json({ kind, content_type: file.type, file_size_bytes: file.size }) },
      );
      const path = await uploadSigned(file, signed);
      return client.request<{ duplicate_flags: number }>(
        `/vendor/businesses/${businessId}/branches/${branchId}/evidence`,
        {
          method: "PUT",
          ...json({
            kind,
            storage_path: path,
            proof_type: proofType,
            content_sha256: await sha256Hex(file),
          }),
        },
      );
    },
    submit: (businessId: string, branchId: string) =>
      client.request<Branch>(`/vendor/businesses/${businessId}/branches/${branchId}/submit`, {
        method: "POST",
      }),
  };
}
