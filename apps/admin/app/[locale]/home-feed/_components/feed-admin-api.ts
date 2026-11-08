"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const feedAdminApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export const SECTION_TYPES = [
  "category",
  "collection",
  "rule",
  "services",
  "events",
  "vendors",
  "for_you",
  "ad_slot",
] as const;
export type SectionType = (typeof SECTION_TYPES)[number];

export const SECTION_LAYOUTS = ["rail", "grid", "banner", "ad"] as const;
export type SectionLayout = (typeof SECTION_LAYOUTS)[number];

export const RULE_SORTS = ["relevance", "newest", "cheapest", "top_rated", "trending"] as const;
export const AUDIENCES = ["all", "guest", "signed_in"] as const;

export type SectionRule = {
  category_paths?: string[];
  price_min_ngwee?: number | null;
  price_max_ngwee?: number | null;
  product_classes?: string[];
  min_rating?: number | null;
  keywords?: string[];
  new_within_days?: number | null;
  sort?: (typeof RULE_SORTS)[number];
};

export type SectionConfig = {
  limit?: number;
  category_path?: string | null;
  listing_ids?: string[];
  rule?: SectionRule | null;
  within_days?: number | null;
  view_all_href?: string | null;
};

export type FeedSectionRow = {
  id: string;
  key: string;
  section_type: SectionType;
  layout: SectionLayout;
  title_key: string | null;
  title_i18n: Record<string, string>;
  config: SectionConfig;
  position: number;
  enabled: boolean;
  starts_at: string | null;
  ends_at: string | null;
  audience: (typeof AUDIENCES)[number];
  live: boolean;
};

export type PreviewPage = {
  sections: Array<{
    id: string;
    key: string;
    section_type: SectionType;
    listings: unknown[];
    services: unknown[];
    events: unknown[];
    vendors: unknown[];
    ad: { headline: string; advertiser_name: string } | null;
  }>;
  carousel: Array<{ placement_id: string; headline: string; advertiser_name: string }>;
  next_cursor: string | null;
};

export function toLocalDatetime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fromLocalDatetime(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/**
 * Parse a kwacha amount typed by an admin ("100", "1,250.5") into integer ngwee
 * using string arithmetic only — never floats on money. Returns null if invalid.
 */
export function parseKwachaToNgwee(input: string): number | null {
  const cleaned = input.trim().replace(/,/g, "").replace(/^K/i, "");
  const match = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) return null;
  const whole = match[1] ?? "0";
  const fraction = (match[2] ?? "").padEnd(2, "0");
  return Number.parseInt(whole, 10) * 100 + Number.parseInt(fraction || "0", 10);
}

/** Integer ngwee → editable kwacha string (no float division). */
export function ngweeToKwachaInput(ngwee: number | null | undefined): string {
  if (ngwee === null || ngwee === undefined) return "";
  const whole = Math.trunc(ngwee / 100);
  const fraction = String(ngwee % 100).padStart(2, "0");
  return fraction === "00" ? String(whole) : `${whole}.${fraction}`;
}

export function splitList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** Move an item up/down; returns a new array (pure, unit-tested). */
export function moveItem<T>(items: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= items.length) return items;
  const next = items.slice();
  const [item] = next.splice(index, 1);
  if (item === undefined) return items;
  next.splice(target, 0, item);
  return next;
}
