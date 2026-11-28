import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type VerifyPickupResponse = {
  order_id: string;
  from_status: string;
  to_status: string;
  event: string;
  token_version: number;
};

export type PickupReadyOrder = {
  id: string;
  preview_title: string;
  status: string;
  fulfilment: string;
};

export function createPickupClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    listReadyForPickup(): Promise<PickupReadyOrder[]> {
      const query = new URLSearchParams({ status: "ready" });
      return client.request<PickupReadyOrder[]>(`/vendor/orders/queue?${query.toString()}`);
    },
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
