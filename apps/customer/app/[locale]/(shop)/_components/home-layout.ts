import { hasDefaultHomeContent, type HomeDefaultData } from "./home-default";
import {
  filterActiveSlots,
  hasEffectiveMerchConfig,
  hasSubstantiveMerchSlot,
  HOME_SECTION_ORDER,
  pickSlot,
  type CategoryRow,
  type HomeSectionKey,
  type MerchSlotRow,
} from "./merch-data";

export type HomeLayoutMode = "hybrid" | "merch" | "default" | "hero-only";

export type HomeLayoutPlan = {
  mode: HomeLayoutMode;
  /** Substantive campaign modules to render (hero only when it is a real campaign). */
  campaignSectionKeys: HomeSectionKey[];
  useCampaignHero: boolean;
  useDefaultHero: boolean;
  showCategoryGrid: boolean;
  showDefaultRails: boolean;
  showSellCta: boolean;
};

/**
 * Campaign section keys that actually have buyer-visible content.
 * `category_grid` is included when catalogue categories exist (tiles are data-driven).
 */
export function getCampaignSectionKeys(
  slots: MerchSlotRow[],
  categories: CategoryRow[],
  now: Date = new Date(),
): HomeSectionKey[] {
  const active = filterActiveSlots(slots, now);

  return HOME_SECTION_ORDER.filter((sectionKey) => {
    if (sectionKey === "category_grid") {
      return categories.length > 0;
    }

    const slot = pickSlot(active, sectionKey);
    if (!slot) {
      return false;
    }

    return hasSubstantiveMerchSlot(slot, now);
  });
}

/**
 * Pure routing decision for the shop homepage — keeps page.tsx thin and testable.
 *
 * Partial/campaign merchandising never erases catalogue rails: when both exist we
 * use `hybrid` (configured slots first, then default discovery).
 */
export function planHomeLayout(
  slots: MerchSlotRow[],
  categories: CategoryRow[],
  defaultData: HomeDefaultData,
  now: Date = new Date(),
): HomeLayoutPlan {
  const hasMerch = hasEffectiveMerchConfig(slots, now);
  const hasDefault = hasDefaultHomeContent(categories, defaultData);
  const campaignSectionKeys = getCampaignSectionKeys(slots, categories, now);
  const useCampaignHero = campaignSectionKeys.includes("hero");

  let mode: HomeLayoutMode;
  if (hasMerch && hasDefault) {
    mode = "hybrid";
  } else if (hasMerch) {
    mode = "merch";
  } else if (hasDefault) {
    mode = "default";
  } else {
    mode = "hero-only";
  }

  return {
    mode,
    campaignSectionKeys,
    useCampaignHero,
    useDefaultHero: !useCampaignHero && mode !== "merch",
    showCategoryGrid: categories.length > 0,
    showDefaultRails: hasDefault,
    showSellCta: hasDefault,
  };
}

/** @deprecated Prefer `planHomeLayout` — retained for existing call sites/tests. */
export function resolveHomeLayoutMode(
  slots: MerchSlotRow[],
  categories: CategoryRow[],
  defaultData: HomeDefaultData,
  now: Date = new Date(),
): HomeLayoutMode {
  return planHomeLayout(slots, categories, defaultData, now).mode;
}
