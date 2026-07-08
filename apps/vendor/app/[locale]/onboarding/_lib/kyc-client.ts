/**
 * M12-P02 KYC endpoint contract (assumed for Wave-6 integration).
 *
 * GET    /kyc/application              → current draft / status
 * PATCH  /kyc/application/draft        → save partial draft fields
 * POST   /kyc/application/submit       → draft → submitted (vendor → pending_kyc)
 * POST   /kyc/application/resubmit     → resubmit after rejected|resubmit
 *
 * Doc uploads use POST /media/sign with resource_kind=kyc_doc (private bucket).
 */
import { createApiClient } from "@vergeo/config";

import type { KycApplication, KycDocType } from "./types";

export type DraftPatch = {
  business_name?: string;
  business_category?: string;
  momo_phone?: string;
  nrc_path?: string | null;
  selfie_path?: string | null;
};

export type ResubmitPayload = {
  nrc_path?: string;
  selfie_path?: string;
  momo_phone?: string;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createKycClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getApplication(): Promise<KycApplication> {
      return client.request<KycApplication>("/kyc/application");
    },

    saveDraft(patch: DraftPatch): Promise<KycApplication> {
      return client.request<KycApplication>("/kyc/application/draft", {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
    },

    submit(): Promise<KycApplication> {
      return client.request<KycApplication>("/kyc/application/submit", {
        method: "POST",
      });
    },

    resubmit(payload: ResubmitPayload): Promise<KycApplication> {
      return client.request<KycApplication>("/kyc/application/resubmit", {
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
