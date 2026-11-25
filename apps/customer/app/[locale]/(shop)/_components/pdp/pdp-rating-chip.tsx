import Link from "next/link";

export type PdpRatingChipProps = {
  locale: string;
  productSlug: string;
  ratingAvg: number;
  ratingCount: number;
  photoReviewCount: number;
  starsAriaLabel: string;
  ratingSummary: string;
  photoReviewsLink: string;
};

export function PdpRatingChip({
  locale,
  productSlug,
  ratingAvg,
  ratingCount,
  photoReviewCount,
  starsAriaLabel,
  ratingSummary,
  photoReviewsLink,
}: PdpRatingChipProps) {
  if (ratingCount <= 0 || ratingAvg <= 0) {
    return null;
  }
  const rounded = Math.max(0, Math.min(5, Math.round(ratingAvg * 2) / 2));
  return (
    <div className="flex flex-col gap-1" data-testid="pdp-rating-chip">
      <Link
        href={`/${locale}/p/${encodeURIComponent(productSlug)}#reviews`}
        className="inline-flex min-h-11 w-fit items-center gap-2 rounded-full border border-border bg-bg px-3 py-1 text-sm font-medium text-text hover:border-primary"
        aria-label={starsAriaLabel}
      >
        <span aria-hidden className="text-warning">
          {"★".repeat(Math.floor(rounded))}
          {rounded % 1 >= 0.5 ? "½" : ""}
          {"☆".repeat(5 - Math.ceil(rounded))}
        </span>
        <span>{ratingSummary}</span>
      </Link>
      {photoReviewCount > 0 ? (
        <Link
          href={`/${locale}/p/${encodeURIComponent(productSlug)}#reviews`}
          className="text-sm text-primary underline-offset-2 hover:underline"
          data-testid="pdp-photo-reviews-link"
        >
          {photoReviewsLink}
        </Link>
      ) : null}
    </div>
  );
}
