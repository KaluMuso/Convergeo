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
