import { createApiClient } from "@vergeo/config";

export type CompletenessBreakdown = {
  logo: boolean;
  description: boolean;
  hours: boolean;
  location: boolean;
  badge: boolean;
};

export type VendorProfile = {
  vendor_id: string;
  slug: string;
  display_name: string;
  description: string | null;
  logo_url: string | null;
  whatsapp_msisdn: string | null;
  preferred_badge: boolean;
  kyc_tier: number | null;
  status: string;
  hours: Record<string, { open?: string; close?: string; closed?: boolean }>;
  lat: number | null;
  lng: number | null;
  landmark: string | null;
  slug_locked: boolean;
  previous_slug: string | null;
  completeness_score: number;
  completeness: CompletenessBreakdown;
};

export type ProfilePatchPayload = {
  display_name?: string;
  description?: string;
  logo_url?: string;
  slug?: string;
  whatsapp_msisdn?: string;
  hours?: Record<string, { open?: string; close?: string; closed?: boolean }>;
  location?: {
    lat: number;
    lng: number;
    landmark: string;
  };
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createProfileClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getProfile(): Promise<VendorProfile> {
      return client.request<VendorProfile>("/vendor/profile");
    },

    updateProfile(payload: ProfilePatchPayload): Promise<VendorProfile> {
      return client.request<VendorProfile>("/vendor/profile", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },
  };
}
