import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type Profile = {
  id: string;
  phone: string | null;
  display_name: string | null;
  locale: string;
};

export type Address = {
  id: string;
  label: string | null;
  landmark: string;
  lat: number | null;
  lng: number | null;
  phone: string | null;
};

export type NotificationPrefs = {
  whatsapp: boolean;
  sms: boolean;
  email: boolean;
};

export type OnboardingState = {
  interests: string[];
  completed_at: string | null;
};

export type PreferencesResponse = {
  notif_prefs: NotificationPrefs;
  onboarding: OnboardingState;
};

export type AddressInput = {
  label?: string | null;
  landmark: string;
  lat?: number | null;
  lng?: number | null;
  phone?: string | null;
};

export type Birthday = {
  day: number | null;
  month: number | null;
  year: number | null;
  consented: boolean;
  /** ISO date from which day/month may change again; null = now. */
  can_change_from: string | null;
};

export type BirthdayInput = {
  day: number;
  month: number;
  year: number | null;
  consent: boolean;
  adult_confirmed: boolean;
};

export function createAccountApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getProfile: () => client.request<Profile>("/account/profile"),
    getBirthday: () => client.request<Birthday>("/account/birthday"),
    putBirthday: (body: BirthdayInput) =>
      client.request<Birthday>("/account/birthday", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteBirthday: () => client.request<Birthday>("/account/birthday", { method: "DELETE" }),
    patchProfile: (body: { display_name?: string | null; locale?: string }) =>
      client.request<Profile>("/account/profile", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    listAddresses: () => client.request<Address[]>("/account/addresses"),
    createAddress: (body: AddressInput) =>
      client.request<Address>("/account/addresses", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    patchAddress: (id: string, body: Partial<AddressInput>) =>
      client.request<Address>(`/account/addresses/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    deleteAddress: (id: string) =>
      client.request<void>(`/account/addresses/${id}`, { method: "DELETE" }),
    getPreferences: () => client.request<PreferencesResponse>("/account/preferences"),
    patchPreferences: (body: Partial<NotificationPrefs>) =>
      client.request<PreferencesResponse>("/account/preferences", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    completeOnboarding: (body: { interests: string[]; locale?: string }) =>
      client.request<PreferencesResponse>("/account/onboarding", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
  };
}
