"use client";

import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ListingGrid,
  type CatalogListing,
} from "../../../(shop)/_components/plp/listing-grid";
import {
  fetchFollowFeed,
  type FollowFeedItem,
} from "../../../../../lib/engagement-api";

export type FollowFeedLabels = {
  title: string;
  description: string;
  emptyTitle: string;
  emptyBody: string;
  browseVendors: string;
  signIn: string;
  signInCta: string;
  loadFailed: string;
  retry: string;
  loadMore: string;
  loading: string;
  grid: Parameters<typeof ListingGrid>[0]["labels"];
};

function toListing(item: FollowFeedItem): CatalogListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    oldNgwee: item.compare_at_ngwee ?? undefined,
    condition: item.condition,
    inStock: item.in_stock,
    imagePublicId: item.image_public_id,
    rating: item.rating,
    reviewCount: item.review_count,
    distanceM: item.distance_m,
    belowMedian: false,
    deliveryAvailable: item.delivery_available ?? false,
    pickupAvailable: item.pickup_available ?? false,
    fulfilmentMode: item.fulfilment_mode,
    leadTimeDays: item.lead_time_days ?? null,
  };
}

/** New listings from followed stores (GET /me/follows/feed, offset-paged). */
export function FollowFeedPanel({
  locale,
  labels,
}: {
  locale: string;
  labels: FollowFeedLabels;
}) {
  const [items, setItems] = useState<CatalogListing[]>([]);
  const [state, setState] = useState<
    "loading" | "ready" | "signed_out" | "error"
  >("loading");
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [moreBusy, setMoreBusy] = useState(false);

  const load = useCallback(async (offset: number) => {
    const result = await fetchFollowFeed(offset);
    if (result === "signed_out") {
      setState("signed_out");
      return;
    }
    if (result === null) {
      setState((current) => (offset === 0 ? "error" : current));
      return;
    }
    setItems((current) =>
      (offset === 0 ? [] : current).concat(result.items.map(toListing)),
    );
    setNextOffset(result.next_offset);
    setState("ready");
  }, []);

  useEffect(() => {
    void load(0);
  }, [load]);

  return (
    <section className="flex flex-col gap-4" data-testid="follow-feed">
      <div>
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">
          {labels.title}
        </h1>
        <p className="m-0 mt-1 text-sm text-text-2">{labels.description}</p>
      </div>
      {state === "loading" ? (
        <p role="status" className="text-sm text-text-2">
          {labels.loading}
        </p>
      ) : state === "signed_out" ? (
        <EmptyState
          title={labels.signIn}
          action={
            <LinkButton
              href={`/${locale}/login?next=${encodeURIComponent(`/${locale}/account/following`)}`}
              variant="primary"
              LinkComponent={Link}
            >
              {labels.signInCta}
            </LinkButton>
          }
        />
      ) : state === "error" ? (
        <EmptyState
          title={labels.loadFailed}
          action={
            <button
              type="button"
              onClick={() => {
                setState("loading");
                void load(0);
              }}
              className="inline-flex min-h-11 items-center rounded-pill border border-border px-4 text-sm font-semibold"
            >
              {labels.retry}
            </button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          title={labels.emptyTitle}
          body={labels.emptyBody}
          action={
            <LinkButton
              href={`/${locale}/vendors`}
              variant="primary"
              LinkComponent={Link}
            >
              {labels.browseVendors}
            </LinkButton>
          }
        />
      ) : (
        <>
          <ListingGrid locale={locale} listings={items} labels={labels.grid} />
          {nextOffset !== null ? (
            <button
              type="button"
              disabled={moreBusy}
              onClick={() => {
                setMoreBusy(true);
                void load(nextOffset).finally(() => setMoreBusy(false));
              }}
              className="mx-auto inline-flex min-h-11 items-center rounded-pill border border-border px-5 text-sm font-semibold text-text hover:border-primary disabled:opacity-60"
            >
              {labels.loadMore}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}
