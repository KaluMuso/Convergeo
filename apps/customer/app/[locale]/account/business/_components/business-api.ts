import { createApiClient } from "@vergeo/config";

export type BusinessStatusValue = "pending" | "verified" | "rejected" | "suspended";

export type BusinessStatus = {
  has_application: boolean;
  status: BusinessStatusValue | null;
  eligible: boolean;
  legal_name: string | null;
  registration_no: string | null;
  tpin: string | null;
  reviewer_notes: string | null;
};

export type BusinessApplyBody = {
  legal_name: string;
  registration_no: string;
  tpin?: string | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createBusinessApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getStatus(): Promise<BusinessStatus> {
      return client.request<BusinessStatus>("/business/status");
    },
    apply(body: BusinessApplyBody): Promise<BusinessStatus> {
      return client.request<BusinessStatus>("/business/apply", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  };
}
