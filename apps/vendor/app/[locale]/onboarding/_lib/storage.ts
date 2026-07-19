import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

import { PRIVATE_KYC_BUCKET, type KycDocType } from "./types";

export type KycSignUploadRequest = {
  resource_kind: "kyc_doc";
  doc_type: KycDocType;
  file_size_bytes: number;
};

export type KycSignUploadResponse = {
  bucket: string;
  path: string;
  token: string;
  signed_url: string;
};

const KYC_DOC_PATH_PREFIX = "kyc/";

export function isPrivateKycPath(path: string): boolean {
  const normalized = path.replace(/^\/+/, "");
  return normalized.startsWith(KYC_DOC_PATH_PREFIX) && !normalized.includes("..");
}

export function assertPrivateKycPath(path: string): void {
  if (!isPrivateKycPath(path)) {
    throw new Error("KYC documents must use private bucket paths under kyc/");
  }
}

export function createStorageClient(getToken: () => string | null | Promise<string | null>) {
  const apiBase = getApiBaseUrl();
  const client = createApiClient({ baseUrl: apiBase, getToken });

  return {
    async signKycUpload(
      docType: KycDocType,
      fileSizeBytes: number,
    ): Promise<KycSignUploadResponse> {
      const response = await client.request<KycSignUploadResponse>("/media/kyc-doc/sign", {
        method: "POST",
        body: JSON.stringify({
          resource_kind: "kyc_doc",
          doc_type: docType,
          file_size_bytes: fileSizeBytes,
        } satisfies KycSignUploadRequest),
      });

      if (response.bucket !== PRIVATE_KYC_BUCKET) {
        throw new Error("KYC uploads must target the private bucket");
      }

      assertPrivateKycPath(response.path);
      return response;
    },

    async uploadSigned(file: Blob, signed: KycSignUploadResponse): Promise<string> {
      const headers = new Headers();
      headers.set("Content-Type", file.type || "image/jpeg");
      if (signed.token) {
        headers.set("x-upsert", "false");
      }

      const response = await fetch(signed.signed_url, {
        method: "PUT",
        headers,
        body: file,
      });

      if (!response.ok) {
        throw new Error("Signed upload failed");
      }

      return signed.path;
    },
  };
}
