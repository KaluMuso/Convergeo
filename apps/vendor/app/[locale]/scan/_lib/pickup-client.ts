import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type VerifyPickupResponse = {
  order_id: string;
  from_status: string;
  to_status: string;
  event: string;
  token_version: number;
};

export function createPickupClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    verifyQr(qrToken: string): Promise<VerifyPickupResponse> {
      return client.request<VerifyPickupResponse>("/vendor/pickup/verify", {
        method: "POST",
        body: JSON.stringify({ qr_token: qrToken }),
      });
    },
    verifyPin(orderId: string, pin: string): Promise<VerifyPickupResponse> {
      return client.request<VerifyPickupResponse>("/vendor/pickup/verify", {
        method: "POST",
        body: JSON.stringify({ order_id: orderId, pin }),
      });
    },
  };
}
