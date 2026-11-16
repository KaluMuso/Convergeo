import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

import type { Checklist, EventDraftFields } from "./collab-readiness";

export type CollabStatusName =
  | "draft"
  | "submitted"
  | "changes_requested"
  | "approved"
  | "declined"
  | "published";

export type CollabFlagStatus = {
  enabled: boolean;
  can_organise: boolean;
  accepts_requests: boolean;
};

export type OrganiserOption = {
  vendor_id: string;
  slug: string;
  display_name: string;
  blurb: string | null;
};

export type CollabParty = {
  vendor_id: string;
  display_name: string;
  slug: string | null;
};

export type CollabAudit = {
  action: string;
  actor_role: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  created_at: string;
};

export type CollabRequest = {
  id: string;
  status: CollabStatusName;
  my_role: "proposer" | "organiser";
  proposer: CollabParty;
  organiser: CollabParty;
  event_draft: Record<string, unknown>;
  checklist: Record<string, unknown>;
  readiness_pct: number;
  revenue_share_bps: number | null;
  organiser_note: string | null;
  event_id: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  audit: CollabAudit[];
};

export type CollabWritePayload = {
  event_draft: Partial<EventDraftFields>;
  checklist: Checklist;
  revenue_share_bps: number | null;
};

function compactDraft(
  draft: Partial<EventDraftFields>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(draft)) {
    if (typeof value === "string" && value.trim()) {
      out[key] = value.trim();
    }
  }
  return out;
}

const BASE = "/vendor/event-collaboration";

export function createCollabClient(
  getToken: () => string | null | Promise<string | null>,
) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  const post = <T>(path: string, body?: unknown) =>
    client.request<T>(`${BASE}${path}`, {
      method: "POST",
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });

  return {
    getStatus: () => client.request<CollabFlagStatus>(`${BASE}/status`),
    setOrganiserSettings: (accepts_requests: boolean) =>
      client.request<CollabFlagStatus>(`${BASE}/organiser-settings`, {
        method: "PUT",
        body: JSON.stringify({ accepts_requests }),
      }),
    listOrganisers: (q: string) =>
      client.request<{ items: OrganiserOption[] }>(
        `${BASE}/organisers${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
      ),
    listRequests: (role: "proposer" | "organiser") =>
      client.request<{ items: CollabRequest[] }>(
        `${BASE}/requests?role=${role}`,
      ),
    getRequest: (id: string) =>
      client.request<CollabRequest>(`${BASE}/requests/${id}`),
    createRequest: (organiserVendorId: string, payload: CollabWritePayload) =>
      post<CollabRequest>("/requests", {
        organiser_vendor_id: organiserVendorId,
        event_draft: compactDraft(payload.event_draft),
        checklist: payload.checklist,
        revenue_share_bps: payload.revenue_share_bps,
      }),
    updateRequest: (id: string, payload: CollabWritePayload) =>
      client.request<CollabRequest>(`${BASE}/requests/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          event_draft: compactDraft(payload.event_draft),
          checklist: payload.checklist,
          revenue_share_bps: payload.revenue_share_bps,
        }),
      }),
    submit: (id: string) => post<CollabRequest>(`/requests/${id}/submit`),
    approve: (id: string) => post<CollabRequest>(`/requests/${id}/approve`),
    decline: (id: string, reason: string) =>
      post<CollabRequest>(`/requests/${id}/decline`, { reason }),
    requestChanges: (id: string, reason: string) =>
      post<CollabRequest>(`/requests/${id}/request-changes`, { reason }),
    publish: (id: string) => post<CollabRequest>(`/requests/${id}/publish`),
  };
}

export type CollabClient = ReturnType<typeof createCollabClient>;
