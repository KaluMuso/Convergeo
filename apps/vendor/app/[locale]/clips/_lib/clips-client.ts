import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

/** The clip lifecycle, exactly as the API reports it. */
export type ClipStatus =
  "draft" | "screening" | "pending_review" | "published" | "rejected" | "taken_down";

/**
 * Statuses that mean "shoppers can see this". Exported as a set so the studio
 * cannot accidentally imply a clip is live: anything not in here renders with
 * the awaiting/processing tone, and a new status added later defaults to *not*
 * live rather than to live.
 */
export const LIVE_STATUSES: ReadonlySet<string> = new Set<ClipStatus>(["published"]);

export type ClipLink = {
  listing_id: string;
  title: string | null;
  price_ngwee: number;
  sort_order: number;
};

export type VendorClip = {
  id: string;
  status: ClipStatus | string;
  caption: string | null;
  category_id: string | null;
  poster_url: string | null;
  duration_s: number | null;
  renditions: Record<string, unknown>;
  like_count: number;
  comment_count: number;
  view_count: number;
  rejection_reason: string | null;
  published_at: string | null;
  taken_down_at: string | null;
  created_at: string | null;
  listings: ClipLink[];
};

export type VendorClipList = {
  items: VendorClip[];
  weekly_cap: number;
  remaining_this_week: number;
  window_days: number;
};

export type ClipStats = {
  clip_id: string;
  status: string;
  view_count: number;
  like_count: number;
  comment_count: number;
  orders_attributed: number;
};

/** Signed direct-upload parameters from `POST /clips`. Never an `api_secret`. */
export type SignedClipUpload = {
  clip_id: string;
  status: string;
  cloud_name: string;
  api_key: string;
  timestamp: number;
  signature: string;
  folder: string;
  allowed_formats: string;
  max_file_size: number;
  eager: string;
  eager_async: string;
  duration: number;
  public_id?: string | null;
  notification_url?: string | null;
  eager_notification_url?: string | null;
};

export function createClipsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    list(): Promise<VendorClipList> {
      return client.request<VendorClipList>("/vendor/clips");
    },

    stats(clipId: string): Promise<ClipStats> {
      return client.request<ClipStats>(`/vendor/clips/${encodeURIComponent(clipId)}/stats`);
    },

    /**
     * Create the draft and get signed upload params. The server screens the
     * caption and enforces the weekly cap here, so this is also where an
     * over-quota or prohibited attempt is refused — before any bytes move.
     */
    createDraft(body: {
      caption?: string | null;
      category_id?: string | null;
      file_size_bytes?: number;
      duration_s?: number;
    }): Promise<SignedClipUpload> {
      return client.request<SignedClipUpload>("/clips", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },

    linkListing(clipId: string, listingId: string, sortOrder = 0) {
      return client.request<{ clip_id: string; listings: ClipLink[] }>(
        `/vendor/clips/${encodeURIComponent(clipId)}/listings`,
        { method: "POST", body: JSON.stringify({ listing_id: listingId, sort_order: sortOrder }) },
      );
    },

    unlinkListing(clipId: string, listingId: string) {
      return client.request<{ clip_id: string; listings: ClipLink[] }>(
        `/vendor/clips/${encodeURIComponent(clipId)}/listings/${encodeURIComponent(listingId)}`,
        { method: "DELETE" },
      );
    },
  };
}
