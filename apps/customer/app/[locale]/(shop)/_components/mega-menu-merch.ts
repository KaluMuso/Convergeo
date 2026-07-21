import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type MegaMenuMini = {
  title: string;
  href: string;
  priceLabel?: string;
};

export type MegaMenuMerchPayload = {
  featuredMinis: MegaMenuMini[];
  promoText: string | null;
  promoCtaLabel: string | null;
  promoHref: string;
};

const LOCALES = new Set(["en", "bem", "nya", "fr", "zh"]);

/** Prefix locale when admin enters a root-relative path without locale segment. */
export function withLocaleHref(locale: string, href: string): string {
  if (!href.startsWith("/")) {
    return href;
  }
  const segment = href.split("/").filter(Boolean)[0];
  if (segment && LOCALES.has(segment)) {
    return href;
  }
  return `/${locale}${href}`;
}

type MerchSlotRow = {
  slot_key: string;
  payload: Record<string, unknown>;
  active: boolean;
  schedule_from: string | null;
  schedule_to: string | null;
};

function isActiveSlot(row: MerchSlotRow, now: Date = new Date()): boolean {
  if (!row.active) {
    return false;
  }
  if (row.schedule_from) {
    const from = new Date(row.schedule_from);
    if (now < from) {
      return false;
    }
  }
  if (row.schedule_to) {
    const to = new Date(row.schedule_to);
    if (now > to) {
      return false;
    }
  }
  return true;
}

function parseFeaturedMinis(raw: unknown): MegaMenuMini[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((entry) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }
    const record = entry as Record<string, unknown>;
    const title = typeof record.title === "string" ? record.title.trim() : "";
    const href = typeof record.href === "string" ? record.href.trim() : "";
    if (!title || !href) {
      return [];
    }
    const priceLabel =
      typeof record.price_label === "string" && record.price_label.trim().length > 0
        ? record.price_label.trim()
        : undefined;
    return [{ title, href, priceLabel }];
  });
}

/** Parse a `mega_menu` merch_slots payload (admin CMS). */
export function parseMegaMenuMerchPayload(payload: Record<string, unknown>): MegaMenuMerchPayload {
  const promoText =
    typeof payload.promo_text === "string" && payload.promo_text.trim().length > 0
      ? payload.promo_text.trim()
      : null;
  const promoCtaLabel =
    typeof payload.promo_cta_label === "string" && payload.promo_cta_label.trim().length > 0
      ? payload.promo_cta_label.trim()
      : null;
  const promoHref =
    typeof payload.promo_href === "string" && payload.promo_href.trim().length > 0
      ? payload.promo_href.trim()
      : "/search";

  return {
    featuredMinis: parseFeaturedMinis(payload.featured_minis),
    promoText,
    promoCtaLabel,
    promoHref,
  };
}

export function pickMegaMenuMerchSlot(
  rows: MerchSlotRow[],
  now: Date = new Date(),
): MegaMenuMerchPayload | null {
  const slot = rows.find((row) => row.slot_key === "mega_menu" && isActiveSlot(row, now));
  if (!slot) {
    return null;
  }
  return parseMegaMenuMerchPayload(slot.payload);
}

/** Pick mega_menu from API-resolved slots (schedule already applied server-side). */
export function pickMegaMenuMerchFromResolvedSlots(
  rows: MerchSlotRow[],
): MegaMenuMerchPayload | null {
  const slot = rows.find((row) => row.slot_key === "mega_menu");
  if (!slot) {
    return null;
  }
  return parseMegaMenuMerchPayload(slot.payload);
}

export function readMerchPreviewToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return new URLSearchParams(window.location.search).get("merch_preview");
}

export async function fetchMegaMenuMerchSlot(
  previewToken?: string | null,
): Promise<MegaMenuMerchPayload | null> {
  const baseUrl = getApiBaseUrl();
  if (baseUrl) {
    try {
      const path = previewToken
        ? `/merch/slots?merch_preview=${encodeURIComponent(previewToken)}`
        : "/merch/slots";
      const slots = await createApiClient({ baseUrl }).request<MerchSlotRow[]>(path);
      return pickMegaMenuMerchFromResolvedSlots(slots);
    } catch {
      // Fall through to direct Supabase read.
    }
  }

  try {
    const supabase = await getBrowserClient();
    const { data, error } = await supabase
      .from("merch_slots")
      .select("slot_key, payload, active, schedule_from, schedule_to")
      .eq("slot_key", "mega_menu");
    if (!error && data) {
      return pickMegaMenuMerchSlot(data);
    }
  } catch {
    return null;
  }

  return null;
}
