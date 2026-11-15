import { readLeadTimePhrases, type MadeToOrderLabels } from "../sale-quantity";

import type { DeliveryEstimateLabels } from "../../../../../lib/delivery-estimate";

/** Raw `catalog.delivery.*` templates ({min}/{max} filled by formatDeliveryEstimate). */
export function catalogDeliveryLabels(raw: (key: string) => unknown): DeliveryEstimateLabels {
  const get = (key: string) => String(raw(`delivery.${key}`));
  return {
    deliveryToday: get("deliveryToday"),
    deliveryTomorrow: get("deliveryTomorrow"),
    deliveryDays: get("deliveryDays"),
    pickupToday: get("pickupToday"),
    pickupTomorrow: get("pickupTomorrow"),
    pickupDays: get("pickupDays"),
  };
}

/** `catalog.madeToOrder.*` templates for the "Made to order · ready within a week" badge. */
export function catalogMadeToOrderLabels(raw: (key: string) => unknown): MadeToOrderLabels {
  return {
    badge: String(raw("madeToOrder.badge")),
    when: readLeadTimePhrases((form) => String(raw(`madeToOrder.when.${form}`))),
  };
}
