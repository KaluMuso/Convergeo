import { ngweeToKwachaInput, parseKwachaToNgwee } from "../../home-feed/_components/feed-admin-api";

export const ANALYTICS_DEPTHS = ["basic", "standard", "advanced"] as const;
export type AnalyticsDepth = (typeof ANALYTICS_DEPTHS)[number];

export type VendorPlan = {
  key: string;
  name: string;
  price_ngwee: number;
  max_listings: number | null;
  max_images_per_listing: number;
  featured_slots: number;
  analytics_depth: AnalyticsDepth;
  wholesale_tools: boolean;
  is_default: boolean;
  active: boolean;
  position: number;
  vendor_count: number;
};

export type VendorPlanDetail = {
  vendor_id: string;
  flag_enabled: boolean;
  assignment: {
    plan_key: string;
    source: string;
    billing_status: string;
    note: string | null;
    assigned_at: string | null;
  } | null;
  override: {
    max_listings: number | null;
    unlimited_listings: boolean;
    max_images_per_listing: number | null;
    expires_at: string;
    reason: string;
    live: boolean;
  } | null;
  effective_plan_key: string | null;
  effective_max_listings: number | null;
  effective_max_images_per_listing: number | null;
  listing_count: number;
};

/** Editable form state: money as a kwacha string, "unlimited" as an empty limit. */
export type PlanDraft = {
  key: string;
  name: string;
  price: string;
  maxListings: string;
  maxImages: string;
  featuredSlots: string;
  analyticsDepth: AnalyticsDepth;
  wholesaleTools: boolean;
  active: boolean;
};

export type PlanPayload = {
  name: string;
  price_ngwee: number;
  max_listings: number | null;
  max_images_per_listing: number;
  featured_slots: number;
  analytics_depth: AnalyticsDepth;
  wholesale_tools: boolean;
  active: boolean;
};

export type DraftError =
  | "nameRequired"
  | "keyInvalid"
  | "priceInvalid"
  | "listingsInvalid"
  | "imagesInvalid"
  | "slotsInvalid";

export const EMPTY_DRAFT: PlanDraft = {
  key: "",
  name: "",
  price: "0",
  maxListings: "",
  maxImages: "8",
  featuredSlots: "0",
  analyticsDepth: "basic",
  wholesaleTools: false,
  active: true,
};

export function planToDraft(plan: VendorPlan): PlanDraft {
  return {
    key: plan.key,
    name: plan.name,
    price: ngweeToKwachaInput(plan.price_ngwee),
    maxListings: plan.max_listings === null ? "" : String(plan.max_listings),
    maxImages: String(plan.max_images_per_listing),
    featuredSlots: String(plan.featured_slots),
    analyticsDepth: plan.analytics_depth,
    wholesaleTools: plan.wholesale_tools,
    active: plan.active,
  };
}

function wholeNumber(value: string, min: number, max: number): number | null {
  if (!/^\d{1,7}$/.test(value.trim())) return null;
  const parsed = Number.parseInt(value.trim(), 10);
  return parsed >= min && parsed <= max ? parsed : null;
}

/** Validate a draft into an API payload (integer ngwee; empty listing limit = unlimited). */
export function draftToPayload(
  draft: PlanDraft,
): { ok: true; payload: PlanPayload } | { ok: false; error: DraftError } {
  if (!draft.name.trim()) return { ok: false, error: "nameRequired" };
  const price = parseKwachaToNgwee(draft.price);
  if (price === null || price > 100_000_000) return { ok: false, error: "priceInvalid" };
  let maxListings: number | null = null;
  if (draft.maxListings.trim() !== "") {
    maxListings = wholeNumber(draft.maxListings, 0, 1_000_000);
    if (maxListings === null) return { ok: false, error: "listingsInvalid" };
  }
  const maxImages = wholeNumber(draft.maxImages, 1, 8);
  if (maxImages === null) return { ok: false, error: "imagesInvalid" };
  const slots = wholeNumber(draft.featuredSlots, 0, 100);
  if (slots === null) return { ok: false, error: "slotsInvalid" };
  return {
    ok: true,
    payload: {
      name: draft.name.trim(),
      price_ngwee: price,
      max_listings: maxListings,
      max_images_per_listing: maxImages,
      featured_slots: slots,
      analytics_depth: draft.analyticsDepth,
      wholesale_tools: draft.wholesaleTools,
      active: draft.active,
    },
  };
}

export function isValidPlanKey(key: string): boolean {
  return /^[a-z][a-z0-9_]{1,31}$/.test(key);
}

/** Only the fields that changed — the PATCH body (null max_listings = unlimited). */
export function planPatch(plan: VendorPlan, payload: PlanPayload): Partial<PlanPayload> {
  const patch: Partial<PlanPayload> = {};
  (Object.keys(payload) as (keyof PlanPayload)[]).forEach((field) => {
    if (payload[field] !== plan[field]) {
      (patch as Record<string, unknown>)[field] = payload[field];
    }
  });
  return patch;
}

export type OverrideForm = {
  unlimited: boolean;
  maxListings: string;
  maxImages: string;
  expiresOn: string; // yyyy-mm-dd (local)
  reason: string;
};

export type OverrideError =
  "overrideEmpty" | "listingsInvalid" | "imagesInvalid" | "expiryInvalid" | "reasonRequired";

/** Builds the override body; expiry is the END of the chosen local day, sent with its offset. */
export function overrideToPayload(
  form: OverrideForm,
  now: Date = new Date(),
):
  | {
      ok: true;
      payload: {
        unlimited_listings: boolean;
        max_listings: number | null;
        max_images_per_listing: number | null;
        expires_at: string;
        reason: string;
      };
    }
  | { ok: false; error: OverrideError } {
  const maxListings =
    form.unlimited || form.maxListings.trim() === ""
      ? null
      : wholeNumber(form.maxListings, 0, 1_000_000);
  if (!form.unlimited && form.maxListings.trim() !== "" && maxListings === null) {
    return { ok: false, error: "listingsInvalid" };
  }
  const maxImages = form.maxImages.trim() === "" ? null : wholeNumber(form.maxImages, 1, 8);
  if (form.maxImages.trim() !== "" && maxImages === null) {
    return { ok: false, error: "imagesInvalid" };
  }
  if (!form.unlimited && maxListings === null && maxImages === null) {
    return { ok: false, error: "overrideEmpty" };
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(form.expiresOn);
  if (!match) return { ok: false, error: "expiryInvalid" };
  const expires = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59);
  if (Number.isNaN(expires.getTime()) || expires.getTime() <= now.getTime()) {
    return { ok: false, error: "expiryInvalid" };
  }
  if (!form.reason.trim()) return { ok: false, error: "reasonRequired" };
  return {
    ok: true,
    payload: {
      unlimited_listings: form.unlimited,
      max_listings: form.unlimited ? null : maxListings,
      max_images_per_listing: maxImages,
      expires_at: expires.toISOString(),
      reason: form.reason.trim(),
    },
  };
}

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
