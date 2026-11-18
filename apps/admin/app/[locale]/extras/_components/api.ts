"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { parseKwachaToNgwee } from "../../home-feed/_components/feed-admin-api";

export const extrasApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export const REQUEST_STATUSES = [
  "requested",
  "quoted",
  "approved",
  "fulfilled",
  "cancelled",
] as const;
export type RequestStatus = (typeof REQUEST_STATUSES)[number];
export type TransitionTo = "quoted" | "approved" | "fulfilled" | "cancelled";

export type ExtrasRequest = {
  id: string;
  vendor_id: string;
  vendor_name: string | null;
  vendor_slug: string | null;
  extra_key: string;
  extra_name: string | null;
  quantity: number;
  note: string | null;
  status: RequestStatus;
  quoted_price_ngwee: number | null;
  admin_note: string | null;
  created_at: string | null;
};

export type AdminExtra = {
  key: string;
  name: string;
  description: string;
  pricing: "fixed" | "range" | "pay_as_you_go";
  price_ngwee: number | null;
  price_max_ngwee: number | null;
  unit: "one_off" | "per_month" | "per_item";
  price_is_placeholder: boolean;
  active: boolean;
  position: number;
};

/** Admin actions allowed from each status (mirror of the DB state machine). */
export function adminActions(status: RequestStatus): TransitionTo[] {
  switch (status) {
    case "requested":
    case "quoted":
      return ["quoted", "approved", "cancelled"];
    case "approved":
      return ["fulfilled", "cancelled"];
    default:
      return [];
  }
}

export type TransitionBody = {
  to: TransitionTo;
  note?: string;
  quoted_price_ngwee?: number;
};

/** Build a transition body; a quote needs a valid kwacha amount (integer ngwee). */
export function transitionBody(
  to: TransitionTo,
  quoteText: string,
  note: string,
): TransitionBody | null {
  const body: TransitionBody = { to };
  if (note.trim()) body.note = note.trim();
  if (to === "quoted") {
    const ngwee = parseKwachaToNgwee(quoteText);
    if (ngwee === null) return null;
    body.quoted_price_ngwee = ngwee;
  }
  return body;
}

export type ExtraDraft = {
  name: string;
  description: string;
  pricing: AdminExtra["pricing"];
  price: string;
  priceMax: string;
  unit: AdminExtra["unit"];
  active: boolean;
};

/** Validated PATCH payload (integer ngwee), or null when the price shape is wrong. */
export function extraPayload(
  draft: ExtraDraft,
): Record<string, unknown> | null {
  const price = draft.price.trim() ? parseKwachaToNgwee(draft.price) : null;
  const max = draft.priceMax.trim() ? parseKwachaToNgwee(draft.priceMax) : null;
  if (draft.price.trim() && price === null) return null;
  if (draft.priceMax.trim() && max === null) return null;
  if (!draft.name.trim()) return null;
  if (draft.pricing === "fixed" && (price === null || max !== null))
    return null;
  if (
    draft.pricing === "range" &&
    (price === null || max === null || max <= price)
  )
    return null;
  if (draft.pricing === "pay_as_you_go" && max !== null) return null;
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    pricing: draft.pricing,
    price_ngwee: price,
    price_max_ngwee: max,
    unit: draft.unit,
    active: draft.active,
  };
}

export type TrialRow = {
  business_id: string;
  legal_name: string;
  trial_ends_at: string | null;
  in_trial: boolean;
};

/** A local date (yyyy-mm-dd) as the end of that day in Lusaka (UTC+2), ISO with offset. */
export function trialEndFromDate(date: string): string | null {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? `${date}T23:59:59+02:00` : null;
}
