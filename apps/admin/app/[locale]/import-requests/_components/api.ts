"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { parseKwachaToNgwee } from "../../home-feed/_components/feed-admin-api";

export const importApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export const STATUS_FILTERS = ["submitted", "in_review", "quoted", "closed", "cancelled"] as const;
export type ImportStatus = (typeof STATUS_FILTERS)[number];

export type ImportQuote = {
  id: string;
  total_ngwee: number;
  product_ngwee: number;
  freight_ngwee: number;
  duty_ngwee: number;
  clearing_ngwee: number;
  other_ngwee: number;
};

export type AdminImportRequest = {
  id: string;
  vendor_id: string;
  vendor_name: string | null;
  title: string;
  description: string | null;
  reference_url: string | null;
  quantity: number;
  unit: string;
  target_unit_price_ngwee: number | null;
  destination_city: string | null;
  status: ImportStatus;
  created_at: string;
  latest_quote: ImportQuote | null;
};

export type QuoteDraft = {
  partner: string;
  product: string;
  freight: string;
  duty: string;
  clearing: string;
  other: string;
  leadTime: string;
  validUntil: string;
  notes: string;
};

export const EMPTY_DRAFT: QuoteDraft = {
  partner: "",
  product: "",
  freight: "",
  duty: "",
  clearing: "",
  other: "",
  leadTime: "",
  validUntil: "",
  notes: "",
};

/** Moves an admin may make from a status (mirror of the API state machine). */
export function statusActions(status: ImportStatus): Array<"in_review" | "closed"> {
  switch (status) {
    case "submitted":
      return ["in_review", "closed"];
    case "in_review":
      return ["closed"];
    case "quoted":
      return ["in_review", "closed"];
    default:
      return [];
  }
}

export function canQuote(status: ImportStatus): boolean {
  return status === "submitted" || status === "in_review" || status === "quoted";
}

/** Sum of the lines in integer ngwee; null while a required line is invalid. */
export function draftTotal(draft: QuoteDraft): number | null {
  const required = [draft.product, draft.freight, draft.duty, draft.clearing].map(
    parseKwachaToNgwee,
  );
  const other = draft.other.trim() ? parseKwachaToNgwee(draft.other) : 0;
  if (required.some((value) => value === null) || other === null) return null;
  return (required as number[]).reduce((sum, value) => sum + value, 0) + other;
}

/** Quote request body (integer ngwee lines), or null when any line is invalid. */
export function quoteBody(draft: QuoteDraft): Record<string, unknown> | null {
  if (draftTotal(draft) === null) return null;
  const body: Record<string, unknown> = {
    product_ngwee: parseKwachaToNgwee(draft.product),
    freight_ngwee: parseKwachaToNgwee(draft.freight),
    duty_ngwee: parseKwachaToNgwee(draft.duty),
    clearing_ngwee: parseKwachaToNgwee(draft.clearing),
    other_ngwee: draft.other.trim() ? parseKwachaToNgwee(draft.other) : 0,
  };
  if (draft.partner.trim()) body.partner_label = draft.partner.trim();
  if (draft.notes.trim()) body.notes = draft.notes.trim();
  if (draft.leadTime.trim()) {
    const days = Number(draft.leadTime);
    if (!Number.isInteger(days) || days < 1 || days > 365) return null;
    body.lead_time_days = days;
  }
  if (draft.validUntil.trim()) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.validUntil)) return null;
    body.valid_until = `${draft.validUntil}T23:59:59+02:00`;
  }
  return body;
}
