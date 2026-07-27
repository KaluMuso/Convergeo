/**
 * M17-P04 — the shape of `GET /clips/feed`, which is this route's only data
 * contract (M17-P03 owns it). Nothing here queries Supabase directly.
 */

export type ClipRendition = {
  url: string;
  width: number;
  /** D-V5: the real transcoded size, so the "~2 MB" chip tells the truth. */
  bytes: number | null;
};

export type ClipVendorSummary = {
  vendor_id: string;
  display_name: string | null;
  slug: string | null;
};

export type ClipListing = {
  listing_id: string;
  title: string | null;
  price_ngwee: number;
};

export type Clip = {
  id: string;
  caption: string | null;
  poster_url: string | null;
  duration_s: number | null;
  renditions: Record<string, ClipRendition>;
  like_count: number;
  comment_count: number;
  view_count: number;
  published_at: string | null;
  vendor: ClipVendorSummary;
  listings: ClipListing[];
};

export type ClipFeedPage = {
  items: Clip[];
  next_cursor: string | null;
};
