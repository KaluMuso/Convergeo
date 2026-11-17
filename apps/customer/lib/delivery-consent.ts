import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "./api-base-url";

/**
 * Consent to share name, phone and delivery address with a third-party courier
 * (Zambia Data Protection Act 2021). Stored server-side per account with the notice
 * version and a timestamp; the latest answer wins. Must match
 * services/api/app/routers/consents.py DELIVERY_PARTNER_NOTICE_VERSION.
 */
export const DELIVERY_CONSENT_VERSION = "2026-11-13";

export type DeliveryConsent = {
  purpose: "delivery_partner_share";
  granted: boolean;
  version: string;
  current_version: string;
  recorded_at: string | null;
};

const PATH = "/account/consents/delivery-partner";

function client() {
  return createApiClient({
    baseUrl: getApiBaseUrl(),
    getToken: async () => {
      const supabase = await getBrowserClient();
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    },
  });
}

export async function loadDeliveryConsent(): Promise<DeliveryConsent> {
  return client().request<DeliveryConsent>(PATH, { cache: "no-store" });
}

export async function saveDeliveryConsent(
  granted: boolean,
  source: "settings" | "checkout",
): Promise<DeliveryConsent> {
  return client().request<DeliveryConsent>(PATH, {
    method: "PUT",
    body: JSON.stringify({ granted, source, version: DELIVERY_CONSENT_VERSION }),
  });
}

/** Current only when granted for the notice version now shown. */
export function isConsentCurrent(consent: DeliveryConsent | null): boolean {
  return !!consent && consent.granted && consent.version === DELIVERY_CONSENT_VERSION;
}
