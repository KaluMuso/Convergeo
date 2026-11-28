import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type FreeDeliveryMethod = "platform_courier" | "self_delivery";

export type DeliveryTerms = {
  free_delivery_all: boolean;
  free_delivery_method: FreeDeliveryMethod;
};

export type DeliveryTermsUpdate = Partial<DeliveryTerms>;

const PATH = "/vendor/delivery-terms";

export function createDeliveryTermsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    get: () => client.request<DeliveryTerms>(PATH),
    update: (changes: DeliveryTermsUpdate) =>
      client.request<DeliveryTerms>(PATH, {
        method: "PATCH",
        body: JSON.stringify(changes),
      }),
  };
}

export type DeliveryTermsClient = ReturnType<typeof createDeliveryTermsClient>;

type ApiError = { details?: { message_key?: string } };

/** Message key (under vendor.settings.delivery) for a failed save. */
export function deliveryErrorKey(error: unknown): "rateLimited" | "saveFailed" {
  const key = (error as ApiError | null)?.details?.message_key;
  return key === "vendor.deliveryTerms.errors.rateLimited" ? "rateLimited" : "saveFailed";
}
