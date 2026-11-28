"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const askAuditApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type AskAuditSeverity = "info" | "warning" | "critical";
export type AskAuditStatus = "pending" | "passed" | "flagged" | "error";

export type AskAuditCitedItem = {
  kind: string;
  id: string;
  title: string;
  price_ngwee: number | null;
  price_max_ngwee: number | null;
  /** Locale-less customer path (`/p/slug`); prefix origin + locale to open it. */
  href: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  vendor_href: string | null;
};

export type AskAuditFinding = {
  id: string;
  rule: string;
  severity: AskAuditSeverity;
  reason: string;
  entity_kind: string | null;
  entity_id: string | null;
  entity_href: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  vendor_href: string | null;
  details: Record<string, unknown>;
};

export type AskAuditAnswer = {
  id: string;
  created_at: string;
  query: string;
  answer_text: string;
  model: string | null;
  source: string;
  intent: string | null;
  cached: boolean;
  refused: boolean;
  locale: string | null;
  asker: "customer" | "guest";
  audit_status: AskAuditStatus;
  audit_severity: AskAuditSeverity | null;
  audited_at: string | null;
  citations: AskAuditCitedItem[];
  findings: AskAuditFinding[];
};

export type AskAuditPage = {
  items: AskAuditAnswer[];
  next_before: string | null;
  next_before_id: string | null;
};

export type AskAuditFilters = {
  flaggedOnly: boolean;
  severity: "" | "warning" | "critical";
};

export const ASK_AUDIT_PAGE_SIZE = 25;

/** Query string for `GET /admin/ask-audit` (pure; unit-tested). */
export function askAuditQuery(
  filters: AskAuditFilters,
  cursor?: { before: string; beforeId: string | null },
): string {
  const params = new URLSearchParams({ limit: String(ASK_AUDIT_PAGE_SIZE) });
  if (filters.flaggedOnly) {
    params.set("flagged_only", "true");
  }
  if (filters.severity) {
    params.set("severity", filters.severity);
  }
  if (cursor) {
    params.set("before", cursor.before);
    if (cursor.beforeId) {
      params.set("before_id", cursor.beforeId);
    }
  }
  return params.toString();
}

/** Open a locale-less customer path on the storefront (new tab, never the admin origin). */
export function storefrontUrl(origin: string, locale: string, path: string | null): string | null {
  if (!path || !path.startsWith("/")) {
    return null;
  }
  return `${origin.replace(/\/$/, "")}/${locale}${path}`;
}
