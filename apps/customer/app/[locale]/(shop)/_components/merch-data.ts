import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

export type MerchSlotRow = {
  id: string;
  slot_key: string;
  variant_key: string;
  payload: Record<string, unknown>;
  schedule_from: string | null;
  schedule_to: string | null;
  position: number;
  active: boolean;
};

export type CategoryRow = {
  id: string;
  name: string;
  slug: string;
  path: string;
  position: number;
  parent_id: string | null;
  prohibited: boolean;
};

export type HomeMerchData = {
  slots: MerchSlotRow[];
  categories: CategoryRow[];
};

export const HOME_SECTION_ORDER = [
  "hero",
  "banner_row",
  "flash_deal",
  "events_row",
  "featured_collections",
  "category_grid",
] as const;

export type HomeSectionKey = (typeof HOME_SECTION_ORDER)[number];

export function isSlotInSchedule(
  slot: Pick<MerchSlotRow, "active" | "schedule_from" | "schedule_to">,
  now: Date = new Date(),
): boolean {
  if (!slot.active) {
    return false;
  }

  if (slot.schedule_from) {
    const from = new Date(slot.schedule_from);
    if (now < from) {
      return false;
    }
  }

  if (slot.schedule_to) {
    const to = new Date(slot.schedule_to);
    if (now > to) {
      return false;
    }
  }

  return true;
}

export function filterActiveSlots(slots: MerchSlotRow[], now: Date = new Date()): MerchSlotRow[] {
  return slots
    .filter((slot) => isSlotInSchedule(slot, now))
    .sort((left, right) => left.position - right.position);
}

export function pickSlot(slots: MerchSlotRow[], slotKey: string): MerchSlotRow | undefined {
  return slots.find((slot) => slot.slot_key === slotKey);
}

/** i18n keys for the migration seed hero — operational copy, not buyer-facing. */
export const PLACEHOLDER_HERO_MESSAGE_KEYS = new Set([
  "home.hero.placeholder.title",
  "home.hero.placeholder.subtitle",
  "merch.hero.placeholder.title",
  "merch.hero.placeholder.subtitle",
]);

function readPayloadString(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export function normalizeMerchMessageKey(key: string): string {
  if (key.startsWith("merch.")) {
    return key.replace(/^merch\./, "home.");
  }
  return key;
}

export function isPlaceholderHeroMessageKey(key: string): boolean {
  return (
    PLACEHOLDER_HERO_MESSAGE_KEYS.has(key) ||
    PLACEHOLDER_HERO_MESSAGE_KEYS.has(normalizeMerchMessageKey(key))
  );
}

/**
 * True when the hero slot is the seeded placeholder (ops copy, no campaign assets).
 * Real campaigns may reuse editorial-light but must supply non-placeholder copy or media.
 */
export function isPlaceholderHeroSlot(slot: MerchSlotRow): boolean {
  if (slot.slot_key !== "hero") {
    return false;
  }

  const payload = slot.payload;
  const titleKey = readPayloadString(payload, "title_key");
  const subtitleKey = readPayloadString(payload, "subtitle_key");

  const titleIsPlaceholder = !titleKey || isPlaceholderHeroMessageKey(titleKey);
  const subtitleIsPlaceholder = !subtitleKey || isPlaceholderHeroMessageKey(subtitleKey);

  const hasCampaignAssets =
    readPayloadString(payload, "image_public_id") !== undefined ||
    (Array.isArray(payload.stats) && payload.stats.length > 0);

  return titleIsPlaceholder && subtitleIsPlaceholder && !hasCampaignAssets;
}

function hasBannerRowContent(payload: Record<string, unknown>): boolean {
  const rawItems = payload.items;
  if (!Array.isArray(rawItems)) {
    return false;
  }

  return rawItems.some(
    (entry) =>
      entry &&
      typeof entry === "object" &&
      typeof (entry as Record<string, unknown>).title === "string",
  );
}

function hasFlashDealContent(
  slot: Pick<MerchSlotRow, "payload" | "schedule_to">,
  now: Date,
): boolean {
  const endsAt = readPayloadString(slot.payload, "ends_at") ?? slot.schedule_to ?? undefined;
  if (!endsAt) {
    return false;
  }
  const endsAtMs = new Date(endsAt).getTime();
  return !Number.isNaN(endsAtMs) && endsAtMs > now.getTime();
}

function hasEventsRowContent(payload: Record<string, unknown>): boolean {
  const rawItems = payload.events;
  if (!Array.isArray(rawItems)) {
    return false;
  }

  return rawItems.some((entry) => {
    if (!entry || typeof entry !== "object") {
      return false;
    }
    const record = entry as Record<string, unknown>;
    return (
      typeof record.title === "string" &&
      typeof record.date_label === "string" &&
      typeof record.venue_label === "string"
    );
  });
}

function hasFeaturedCollectionsContent(payload: Record<string, unknown>): boolean {
  const rawCollections = payload.collections;
  if (!Array.isArray(rawCollections)) {
    return false;
  }

  return rawCollections.some((entry) => {
    if (!entry || typeof entry !== "object") {
      return false;
    }
    const record = entry as Record<string, unknown>;
    const hasTitle =
      typeof record.title === "string" ||
      (typeof record.title_key === "string" && record.title_key.length > 0);
    if (!hasTitle) {
      return false;
    }
    const rawItems = record.items;
    return (
      Array.isArray(rawItems) &&
      rawItems.some(
        (item) =>
          item &&
          typeof item === "object" &&
          typeof (item as Record<string, unknown>).title === "string",
      )
    );
  });
}

/**
 * True when a merch slot would render buyer-visible campaign content (not the seed
 * placeholder hero or empty module shells).
 */
export function hasSubstantiveMerchSlot(slot: MerchSlotRow, now: Date = new Date()): boolean {
  if (!isSlotInSchedule(slot, now)) {
    return false;
  }

  switch (slot.slot_key) {
    case "hero":
      return !isPlaceholderHeroSlot(slot);
    case "banner_row":
      return hasBannerRowContent(slot.payload);
    case "flash_deal":
      return hasFlashDealContent(slot, now);
    case "events_row":
      return hasEventsRowContent(slot.payload);
    case "featured_collections":
      return hasFeaturedCollectionsContent(slot.payload);
    case "category_grid":
      // Category tiles are provided by the data-driven fallback; slot alone is not a campaign.
      return false;
    default:
      return false;
  }
}

/**
 * Whether admin merchandising should take precedence over the catalogue-backed default
 * homepage. Placeholder-only seed config (hero ops copy, no other modules) returns false.
 */
export function hasEffectiveMerchConfig(slots: MerchSlotRow[], now: Date = new Date()): boolean {
  return slots.some((slot) => hasSubstantiveMerchSlot(slot, now));
}

export function getRenderableSectionKeys(
  slots: MerchSlotRow[],
  categories: CategoryRow[],
): HomeSectionKey[] {
  const active = filterActiveSlots(slots);

  return HOME_SECTION_ORDER.filter((sectionKey) => {
    if (sectionKey === "category_grid") {
      return categories.length > 0 || pickSlot(active, sectionKey) !== undefined;
    }

    return pickSlot(active, sectionKey) !== undefined;
  });
}

export function getTopLevelCategories(categories: CategoryRow[]): CategoryRow[] {
  return categories
    .filter((category) => !category.prohibited && category.parent_id === null)
    .sort((left, right) => left.position - right.position);
}

async function fetchMerchSlots(): Promise<MerchSlotRow[]> {
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);

  const { data, error } = await supabase
    .from("merch_slots")
    .select("id, slot_key, variant_key, payload, schedule_from, schedule_to, position, active")
    .order("position", { ascending: true });

  if (error || !data) {
    return [];
  }

  return data.map((row) => ({
    ...row,
    payload:
      row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
        ? (row.payload as Record<string, unknown>)
        : {},
  }));
}

async function fetchCategories(): Promise<CategoryRow[]> {
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);

  const { data, error } = await supabase
    .from("categories")
    .select("id, name, slug, path, position, parent_id, prohibited")
    .eq("prohibited", false)
    .order("position", { ascending: true });

  if (error || !data) {
    return [];
  }

  return data;
}

export async function loadHomeMerchData(): Promise<HomeMerchData> {
  const [slots, categories] = await Promise.all([fetchMerchSlots(), fetchCategories()]);

  return {
    slots: filterActiveSlots(slots),
    categories: getTopLevelCategories(categories),
  };
}
