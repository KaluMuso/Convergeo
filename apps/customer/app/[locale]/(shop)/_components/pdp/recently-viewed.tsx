"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";
import { useEffect, useState } from "react";

import { recentlyViewedExcluding, type RecentlyViewedItem } from "./recently-viewed-storage";

export type RecentlyViewedLabels = {
  heading: string;
  vendorFallback: string;
  noReviews: string;
  reviewCount: string;
  quickAdd: string;
  wishlist: string;
  mediaEmpty: string;
};

type RecentlyViewedRailProps = {
  locale: string;
  currentSlug: string;
  labels: RecentlyViewedLabels;
  cloudName?: string;
};

function RecentMedia({
  publicId,
  alt,
  cloudName,
  emptyLabel,
}: {
  publicId: string | null;
  alt: string;
  cloudName?: string;
  emptyLabel: string;
}) {
  if (!publicId) {
    return (
      <div
        className="flex h-full w-full items-center justify-center bg-bg-2"
        role="img"
        aria-label={emptyLabel}
      />
    );
  }
  return (
    <CloudinaryImage
      publicId={publicId}
      alt={alt}
      width={360}
      ratio="4/3"
      cloudName={cloudName}
      className="h-full w-full object-cover"
    />
  );
}

/**
 * Client rail of locally recorded product views. Hidden when empty.
 */
export function RecentlyViewedRail({
  locale,
  currentSlug,
  labels,
  cloudName,
}: RecentlyViewedRailProps) {
  const [items, setItems] = useState<RecentlyViewedItem[]>([]);

  useEffect(() => {
    setItems(recentlyViewedExcluding(currentSlug));
  }, [currentSlug]);

  if (items.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="pdp-recently-viewed-heading"
      className="flex flex-col gap-3"
      data-testid="pdp-recently-viewed"
    >
      <h2 id="pdp-recently-viewed-heading" className="font-display text-lg font-semibold text-text">
        {labels.heading}
      </h2>
      <ul className="m-0 grid list-none grid-cols-2 gap-3 p-0 md:grid-cols-3 lg:grid-cols-4">
        {items.map((item) => (
          <li key={item.slug} className="min-w-0">
            <Link href={`/${locale}/p/${item.slug}`} className="block min-w-0 no-underline">
              {item.fromPriceNgwee !== null ? (
                <ProductCard
                  title={item.name}
                  vendorLabel={labels.vendorFallback}
                  ngwee={item.fromPriceNgwee}
                  rating={0}
                  reviewCount={0}
                  noReviewsLabel={labels.noReviews}
                  reviewCountLabel={labels.reviewCount}
                  quickAddLabel={labels.quickAdd}
                  wishlistLabel={labels.wishlist}
                  mediaEmptyLabel={labels.mediaEmpty}
                  media={
                    <RecentMedia
                      publicId={item.imagePublicId}
                      alt={item.name}
                      cloudName={cloudName}
                      emptyLabel={labels.mediaEmpty}
                    />
                  }
                />
              ) : (
                <article className="card-lift flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1">
                  <div className="aspect-[4/3] bg-bg-2">
                    <RecentMedia
                      publicId={item.imagePublicId}
                      alt={item.name}
                      cloudName={cloudName}
                      emptyLabel={labels.mediaEmpty}
                    />
                  </div>
                  <div className="space-y-1 p-3">
                    <p className="truncate text-sm font-medium text-text">{item.name}</p>
                    <p className="text-xs text-text-2">{labels.vendorFallback}</p>
                  </div>
                </article>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
