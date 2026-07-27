"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export const clipsApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type ClipQueueItem = {
  clip_id: string;
  vendor_id: string;
  vendor_name: string | null;
  status: string;
  caption: string | null;
  poster_url: string | null;
  duration_s: number | null;
  created_at: string | null;
  age_hours: number;
  sla_breached: boolean;
  repeat_offender_count: number;
  media_ready: boolean;
};

export type ClipDetail = {
  clip_id: string;
  vendor_id: string;
  vendor_name: string | null;
  vendor_status: string | null;
  vendor_kyc_tier: number | null;
  status: string;
  caption: string | null;
  category_id: string | null;
  duration_s: number | null;
  poster_url: string | null;
  /** Short-lived preview links over a clip that is NOT public. */
  preview_urls: Record<string, string>;
  preview_expires_in_s: number;
  media_ready: boolean;
  media_problems: string[];
  screen_verdict: string;
  linked_listings: {
    listing_id: string;
    title: string | null;
    price_ngwee: number;
    status: string | null;
  }[];
  report_count: number;
  repeat_offender_count: number;
};

export type ClipActionResult = {
  clip_id: string;
  status: string;
  vendor_suspended?: boolean;
};

export type ReportItem = {
  report_id: string;
  clip_id: string;
  clip_status: string;
  reason: string;
  created_at: string | null;
  age_hours: number;
  sla_breached: boolean;
};

export type ClipAnalytics = {
  cost: {
    month_key: string;
    spend_usd_micros: number;
    cap_usd_micros: number;
    headroom_usd_micros: number;
    uploads_paused: boolean;
  };
  funnel: {
    published_clips: number;
    pending_review: number;
    rejected: number;
    taken_down: number;
    views: number;
    likes: number;
    add_to_carts: number;
    attributed_orders: number;
  };
};

export const adminClipsApi = {
  analytics(): Promise<ClipAnalytics> {
    return clipsApi.request<ClipAnalytics>("/admin/clip-analytics");
  },
  resetKillSwitch(): Promise<{ month_key: string; uploads_paused: boolean; reset: boolean }> {
    return clipsApi.request<{ month_key: string; uploads_paused: boolean; reset: boolean }>(
      "/admin/clip-analytics/reset-kill-switch",
      { method: "POST" },
    );
  },
  queue(): Promise<{ items: ClipQueueItem[] }> {
    return clipsApi.request<{ items: ClipQueueItem[] }>("/admin/clips");
  },
  detail(clipId: string): Promise<ClipDetail> {
    return clipsApi.request<ClipDetail>(`/admin/clips/${encodeURIComponent(clipId)}`);
  },
  approve(clipId: string): Promise<ClipActionResult> {
    return clipsApi.request<ClipActionResult>(
      `/admin/clips/${encodeURIComponent(clipId)}/approve`,
      { method: "POST" },
    );
  },
  reject(clipId: string, reason: string): Promise<ClipActionResult> {
    return clipsApi.request<ClipActionResult>(`/admin/clips/${encodeURIComponent(clipId)}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },
  takedown(clipId: string, reason: string): Promise<ClipActionResult> {
    return clipsApi.request<ClipActionResult>(
      `/admin/clips/${encodeURIComponent(clipId)}/takedown`,
      { method: "POST", body: JSON.stringify({ reason }) },
    );
  },
  reports(): Promise<{ items: ReportItem[] }> {
    return clipsApi.request<{ items: ReportItem[] }>("/admin/clips/reports");
  },
  dismissReport(reportId: string, note?: string) {
    return clipsApi.request<{ report_id: string; outcome: string }>(
      `/admin/clips/reports/${encodeURIComponent(reportId)}/dismiss`,
      { method: "POST", body: JSON.stringify({ note: note ?? null }) },
    );
  },
  upholdReport(reportId: string, note?: string) {
    return clipsApi.request<{ report_id: string; outcome: string; vendor_suspended?: boolean }>(
      `/admin/clips/reports/${encodeURIComponent(reportId)}/uphold`,
      { method: "POST", body: JSON.stringify({ note: note ?? null }) },
    );
  },
};
