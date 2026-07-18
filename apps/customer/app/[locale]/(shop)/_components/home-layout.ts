import { hasDefaultHomeContent, type HomeDefaultData } from "./home-default";
import { hasEffectiveMerchConfig, type CategoryRow, type MerchSlotRow } from "./merch-data";

export type HomeLayoutMode = "merch" | "default" | "hero-only";

/**
 * Pure routing decision for the shop homepage — keeps page.tsx thin and testable.
 */
export function resolveHomeLayoutMode(
  slots: MerchSlotRow[],
  categories: CategoryRow[],
  defaultData: HomeDefaultData,
  now: Date = new Date(),
): HomeLayoutMode {
  if (hasEffectiveMerchConfig(slots, now)) {
    return "merch";
  }
  if (hasDefaultHomeContent(categories, defaultData)) {
    return "default";
  }
  return "hero-only";
}
