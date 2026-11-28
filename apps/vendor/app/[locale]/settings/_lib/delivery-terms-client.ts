import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type FreeDeliveryMethod = "platform_courier" | "self_delivery";

export type ZoneFee = { zone_key: string; label: string; fee_ngwee: number };

export type DeliveryTerms = {
  free_delivery_all: boolean;
  free_delivery_method: FreeDeliveryMethod;
  /** Smallest basket (ngwee) that qualifies for this vendor's free delivery. */
  free_delivery_min_ngwee: number;
  /** Platform floor the minimum can't go below (ngwee). */
  min_floor_ngwee: number;
  /** Courier fee per delivery band, charged to the vendor on a free courier order. */
  zone_fees: ZoneFee[];
};

export type DeliveryTermsUpdate = Partial<
  Pick<DeliveryTerms, "free_delivery_all" | "free_delivery_method" | "free_delivery_min_ngwee">
>;

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
export function deliveryErrorKey(error: unknown): "rateLimited" | "minBelowFloor" | "saveFailed" {
  const key = (error as ApiError | null)?.details?.message_key;
  if (key === "vendor.deliveryTerms.errors.rateLimited") return "rateLimited";
  if (key === "vendor.deliveryTerms.errors.minBelowFloor") return "minBelowFloor";
  return "saveFailed";
}
