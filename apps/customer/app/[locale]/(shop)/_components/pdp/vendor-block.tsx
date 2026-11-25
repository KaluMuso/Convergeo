import { CornerRibbon } from "@vergeo/ui/src/corner-ribbon";
import Link from "next/link";

export type VendorBlockData = {
  slug: string;
  displayName: string;
  preferredBadge: boolean;
  ratingAvg: number | null;
  ratingCount: number;
  landmark: string | null;
  verified?: boolean;
  memberSince?: string | null;
};

export type VendorBlockProps = {
  locale: string;
  vendor: VendorBlockData;
  heading: string;
  preferredBadgeLabel: string;
  noReviewsLabel: string;
  ratingLabel: string;
  viewStoreLabel: string;
  verifiedLabel: string;
  memberSinceLabel: string;
};

export function VendorBlock({
  locale,
  vendor,
  heading,
  preferredBadgeLabel,
  noReviewsLabel,
  ratingLabel,
  viewStoreLabel,
  verifiedLabel,
  memberSinceLabel,
}: VendorBlockProps) {
  const ratingText =
    vendor.ratingAvg !== null && vendor.ratingCount > 0 ? ratingLabel : noReviewsLabel;

  return (
    <section
      data-testid="pdp-vendor-block"
      className="rounded border border-border bg-surface p-4"
      style={{ borderRadius: "var(--r)" }}
    >
      <h2 className="mb-3 font-display text-lg font-semibold text-text">{heading}</h2>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-text">{vendor.displayName}</p>
          {vendor.preferredBadge ? (
            <CornerRibbon trust="preferred" trustLabel={preferredBadgeLabel} />
          ) : null}
        </div>

        <p className="text-sm text-text-2" data-testid="pdp-vendor-rating">
          {ratingText}
        </p>

        {vendor.verified ? (
          <p className="text-sm font-medium text-success" data-testid="pdp-vendor-verified">
            {verifiedLabel}
          </p>
        ) : null}

        {vendor.memberSince ? (
          <p className="text-sm text-text-2" data-testid="pdp-vendor-member-since">
            {memberSinceLabel.replace("{date}", vendor.memberSince)}
          </p>
        ) : null}

        {vendor.landmark ? (
          <p className="text-sm text-text-2" data-testid="pdp-vendor-landmark">
            {vendor.landmark}
          </p>
        ) : null}

        <Link
          href={`/${locale}/v/${vendor.slug}`}
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline"
        >
          {viewStoreLabel}
        </Link>
      </div>
    </section>
  );
}
