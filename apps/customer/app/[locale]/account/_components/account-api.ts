import { createApiClient } from "@vergeo/config";

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

export type AddressInput = {
  label?: string | null;
  landmark: string;
  lat?: number | null;
  lng?: number | null;
  phone?: string | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function createAccountApiClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getProfile: () => client.request<Profile>("/account/profile"),
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
    getPreferences: () =>
      client.request<{ notif_prefs: NotificationPrefs }>("/account/preferences"),
    patchPreferences: (body: Partial<NotificationPrefs>) =>
      client.request<{ notif_prefs: NotificationPrefs }>("/account/preferences", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
  };
}
