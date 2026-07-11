"use client";

import { createApiClient } from "@vergeo/config";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { ImageGallery, type GalleryImage } from "@vergeo/ui/src/media/image-gallery";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type ReviewRow = {
  id: string;
  order_item_id: string;
  rating: number;
  body: string | null;
  photos: string[];
  vendor_reply: string | null;
  vendor_reply_at: string | null;
  created_at: string;
};

export type ReviewsSectionLabels = {
  heading: string;
  empty: string;
  writeCta: string;
  starsAria: string;
  photoAlt: string;
  vendorReply: string;
  galleryPrevious: string;
  galleryNext: string;
  galleryIndicator: string;
  loadError: string;
  loading: string;
  starFilled: string;
  starEmpty: string;
};

type ReviewsSectionProps = {
  locale: string;
  productId: string;
  cloudName?: string;
  labels: ReviewsSectionLabels;
  accessToken?: string;
  eligibleOrderId?: string;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function StarRow({
  rating,
  ariaLabel,
  starFilled,
  starEmpty,
}: {
  rating: number;
  ariaLabel: string;
  starFilled: string;
  starEmpty: string;
}) {
  return (
    <div className="flex items-center gap-0.5" role="img" aria-label={ariaLabel}>
      {Array.from({ length: 5 }, (_, index) => (
        <span
          key={index}
          className={index < rating ? "text-warning" : "text-text-3"}
          aria-hidden="true"
        >
          {index < rating ? starFilled : starEmpty}
        </span>
      ))}
    </div>
  );
}

export function ReviewsSection({
  locale,
  productId,
  cloudName,
  labels,
  accessToken,
  eligibleOrderId,
}: ReviewsSectionProps) {
  const [reviews, setReviews] = useState<ReviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [lightbox, setLightbox] = useState<GalleryImage[] | null>(null);

  const loadReviews = useCallback(async () => {
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: accessToken ? () => accessToken : undefined,
      });
      const rows = await client.request<ReviewRow[]>(
        `/reviews?product_id=${encodeURIComponent(productId)}`,
      );
      setReviews(rows);
    } catch {
      setError(labels.loadError);
    } finally {
      setLoading(false);
    }
  }, [accessToken, labels.loadError, productId]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  const writeHref = useMemo(() => {
    if (!eligibleOrderId) {
      return undefined;
    }
    return `/${locale}/account/orders/${eligibleOrderId}`;
  }, [eligibleOrderId, locale]);

  if (loading) {
    return <p className="text-sm text-text-2">{labels.loading}</p>;
  }

  return (
    <section aria-labelledby="product-reviews-heading" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="product-reviews-heading" className="font-display text-h3 text-display-ink">
          {labels.heading}
        </h2>
        {writeHref ? (
          <Link
            href={writeHref}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
          >
            {labels.writeCta}
          </Link>
        ) : null}
      </div>

      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      {reviews.length === 0 ? (
        <p className="text-sm text-text-2">{labels.empty}</p>
      ) : (
        <ul className="space-y-4">
          {reviews.map((review) => (
            <li key={review.id} className="space-y-3 rounded border border-border bg-surface p-4">
              <StarRow
                rating={review.rating}
                ariaLabel={labels.starsAria.replace("{rating}", String(review.rating))}
                starFilled={labels.starFilled}
                starEmpty={labels.starEmpty}
              />
              {review.body ? <p className="text-sm text-display-ink">{review.body}</p> : null}
              {review.photos.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {review.photos.map((publicId) => (
                    <button
                      key={publicId}
                      type="button"
                      className="h-16 w-16 overflow-hidden rounded border border-border"
                      onClick={() =>
                        setLightbox(
                          review.photos.map((photoId) => ({
                            publicId: photoId,
                            alt: labels.photoAlt,
                          })),
                        )
                      }
                    >
                      <CloudinaryImage
                        publicId={publicId}
                        alt={labels.photoAlt}
                        cloudName={cloudName}
                        ratio={1}
                        width={128}
                        className="h-full w-full"
                      />
                    </button>
                  ))}
                </div>
              ) : null}
              {review.vendor_reply ? (
                <div className="rounded bg-bg-2 px-3 py-2 text-sm">
                  <p className="font-medium text-display-ink">{labels.vendorReply}</p>
                  <p className="text-text-2">{review.vendor_reply}</p>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {lightbox && lightbox.length > 0 ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setLightbox(null)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setLightbox(null);
            }
          }}
        >
          <div
            className="w-full max-w-lg"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
          >
            <ImageGallery
              images={lightbox}
              cloudName={cloudName}
              previousLabel={labels.galleryPrevious}
              nextLabel={labels.galleryNext}
              indicatorLabel={(current, total) =>
                labels.galleryIndicator
                  .replace("{current}", String(current))
                  .replace("{total}", String(total))
              }
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}
