import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

import { absoluteApiUrl } from "../../../../lib/api-base-url";

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

type ResolvedMerchSlotApiRow = {
  id: string;
  slot_key: string;
  variant_key: string;
  payload: Record<string, unknown>;
  schedule_from: string | null;
  schedule_to: string | null;
  position: number;
  active: boolean;
  is_preview?: boolean;
  is_fallback?: boolean;
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
  /** True when `?merch_preview=` was present (draft overlay, not cached for SEO). */
  isPreviewMode?: boolean;
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

export type CategoriesLoadFailureReason = "config" | "unauthorized" | "upstream" | "malformed";

export type CategoriesLoadResult =
  | { ok: true; categories: CategoryRow[] }
  | {
      ok: false;
      reason: CategoriesLoadFailureReason;
      code?: string;
      status?: number;
    };

function isCategoryRow(value: unknown): value is CategoryRow {
  if (!value || typeof value !== "object") {
    return false;
  }
  const row = value as Record<string, unknown>;
  return (
    typeof row.id === "string" &&
    typeof row.name === "string" &&
    typeof row.slug === "string" &&
    typeof row.path === "string" &&
    typeof row.position === "number" &&
    Number.isFinite(row.position) &&
    (row.parent_id === null || typeof row.parent_id === "string") &&
    typeof row.prohibited === "boolean"
  );
}

export function classifyCategoriesQueryError(error: {
  code?: string | null;
  message?: string | null;
  status?: number;
}): CategoriesLoadFailureReason {
  const code = (error.code ?? "").toUpperCase();
  const message = (error.message ?? "").toLowerCase();
  const status = error.status;

  if (
    status === 401 ||
    status === 403 ||
    code === "PGRST301" ||
    code === "42501" ||
    message.includes("jwt") ||
    message.includes("not authorized") ||
    message.includes("permission denied")
  ) {
    return "unauthorized";
  }

  if (
    message.includes("missing required environment variable") ||
    message.includes("next_public_supabase")
  ) {
    return "config";
  }

  return "upstream";
}

/** Structured failure log — no secrets, tokens, cookies, or row payloads. */
export function logCategoriesLoadFailure(details: {
  reason: CategoriesLoadFailureReason;
  code?: string;
  status?: number;
}): void {
  console.error(
    JSON.stringify({
      level: "error",
      event: "customer.categories.load_failed",
      reason: details.reason,
      ...(details.code ? { code: details.code } : {}),
      ...(typeof details.status === "number" ? { status: details.status } : {}),
    }),
  );
}

/**
 * Load the public category catalogue with an explicit success/failure result.
 * Empty success (`ok: true, categories: []`) is distinct from operational failures.
 */
export async function fetchCategoriesResult(): Promise<CategoriesLoadResult> {
  let supabase;
  try {
    const cookieStore = await cookies();
    supabase = createServerClient(cookieStore);
  } catch (error) {
    const reason = classifyCategoriesQueryError({
      message: error instanceof Error ? error.message : "config",
    });
    const failure = { ok: false as const, reason: reason === "unauthorized" ? "config" : reason };
    logCategoriesLoadFailure(failure);
    return failure;
  }

  const { data, error, status } = await supabase
    .from("categories")
    .select("id, name, slug, path, position, parent_id, prohibited")
    .eq("prohibited", false)
    .order("position", { ascending: true });

  if (error) {
    const reason = classifyCategoriesQueryError({
      code: error.code,
      message: error.message,
      status: typeof status === "number" ? status : undefined,
    });
    const failure = {
      ok: false as const,
      reason,
      code: error.code || undefined,
      status: typeof status === "number" ? status : undefined,
    };
    logCategoriesLoadFailure(failure);
    return failure;
  }

  if (!Array.isArray(data)) {
    const failure = { ok: false as const, reason: "malformed" as const };
    logCategoriesLoadFailure(failure);
    return failure;
  }

  if (data.length === 0) {
    return { ok: true, categories: [] };
  }

  const categories = data.filter(isCategoryRow);
  if (categories.length === 0) {
    const failure = { ok: false as const, reason: "malformed" as const };
    logCategoriesLoadFailure(failure);
    return failure;
  }

  return { ok: true, categories };
}

/** Home/merch convenience wrapper — failures degrade to an empty list. */
export async function fetchCategories(): Promise<CategoryRow[]> {
  const result = await fetchCategoriesResult();
  return result.ok ? result.categories : [];
}

export function mapResolvedMerchSlot(row: ResolvedMerchSlotApiRow): MerchSlotRow {
  return {
    id: row.id,
    slot_key: row.slot_key,
    variant_key: row.variant_key,
    payload:
      row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
        ? row.payload
        : {},
    schedule_from: row.schedule_from,
    schedule_to: row.schedule_to,
    position: row.position,
    active: row.active,
  };
}

/** Fetch resolved merchandising slots from the public API (supports draft preview token). */
export async function fetchMerchSlotsFromApi(
  merchPreview?: string | null,
): Promise<MerchSlotRow[]> {
  const query = merchPreview ? `?merch_preview=${encodeURIComponent(merchPreview)}` : "";
  const url = absoluteApiUrl(`/merch/slots${query}`);
  if (!url) {
    return [];
  }

  try {
    const response = await fetch(url, {
      next: merchPreview ? { revalidate: 0 } : { revalidate: 60 },
    });
    if (!response.ok) {
      return [];
    }
    const data: unknown = await response.json();
    if (!Array.isArray(data)) {
      return [];
    }
    return data
      .filter((entry): entry is ResolvedMerchSlotApiRow => {
        return Boolean(entry && typeof entry === "object" && "slot_key" in entry);
      })
      .map((entry) => mapResolvedMerchSlot(entry));
  } catch {
    return [];
  }
}

export type LoadHomeMerchDataOptions = {
  /** When set, loads draft overlays via `GET /merch/slots?merch_preview=…`. */
  merchPreview?: string | null;
};

export async function loadHomeMerchData(
  options: LoadHomeMerchDataOptions = {},
): Promise<HomeMerchData> {
  const { merchPreview = null } = options;
  const isPreviewMode = Boolean(merchPreview?.trim());

  const [rawSlots, categories] = await Promise.all([
    isPreviewMode ? fetchMerchSlotsFromApi(merchPreview) : fetchMerchSlots(),
    fetchCategories(),
  ]);

  return {
    slots: isPreviewMode ? rawSlots : filterActiveSlots(rawSlots),
    categories: getTopLevelCategories(categories),
    isPreviewMode,
  };
}
