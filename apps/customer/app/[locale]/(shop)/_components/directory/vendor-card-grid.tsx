import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { VendorCard } from "@vergeo/ui/src/vendor-card";
import Link from "next/link";

export type DirectoryVendorCard = {
  id: string;
  slug: string;
  displayName: string;
  description: string | null;
  logoUrl: string | null;
  preferredBadge: boolean;
  verified: boolean;
  landmark: string | null;
  categories: string[];
  ratingAvg: number | null;
  ratingCount: number;
  listingCount: number;
  createdAt?: string | null;
};

type VendorCardGridLabels = {
  listings: string;
  reviews: string;
  rating: string;
  noReviews: string;
  verifiedSince: string;
  preferredBadge: string;
  verifiedBadge: string;
  viewProfile: string;
  defaultLocation: string;
  categoryLabels: Record<string, string>;
};

type VendorCardGridProps = {
  locale: string;
  vendors: DirectoryVendorCard[];
  labels: VendorCardGridLabels;
};

function categoryLabel(value: string, labels: Record<string, string>): string {
  if (labels[value]) {
    return labels[value];
  }
  return value.replace(/-/g, " ");
}

function formatVerifiedYear(createdAt: string | null | undefined): string {
  if (!createdAt) {
    return String(new Date().getFullYear());
  }
  const year = new Date(createdAt).getFullYear();
  return Number.isFinite(year) ? String(year) : String(new Date().getFullYear());
}

function isCloudinaryPublicId(value: string): boolean {
  return !value.startsWith("http://") && !value.startsWith("https://");
}

function VendorLogo({ logoUrl }: { logoUrl: string }) {
  if (isCloudinaryPublicId(logoUrl)) {
    return (
      <CloudinaryImage
        publicId={logoUrl}
        alt=""
        width={112}
        ratio="1/1"
        className="h-full w-full object-cover"
      />
    );
  }

  return (
    <div
      aria-hidden
      className="h-full w-full bg-cover bg-center"
      style={{ backgroundImage: `url(${logoUrl})` }}
    />
  );
}

export function VendorCardGrid({ locale, vendors, labels }: VendorCardGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {vendors.map((vendor) => {
        const categoryText =
          vendor.categories.length > 0
            ? vendor.categories
                .map((value) => categoryLabel(value, labels.categoryLabels))
                .join(", ")
            : labels.listings;
        const ratingValue =
          vendor.ratingAvg !== null && vendor.ratingCount > 0
            ? labels.rating
                .replace("{rating}", vendor.ratingAvg.toFixed(1))
                .replace("{count}", String(vendor.ratingCount))
            : labels.noReviews;
        const verifiedLabel = labels.verifiedSince.replace(
          "{year}",
          formatVerifiedYear(vendor.createdAt),
        );

        return (
          <Link
            key={vendor.id}
            href={`/${locale}/v/${vendor.slug}`}
            className="min-w-0 no-underline"
          >
            <VendorCard
              name={vendor.displayName}
              categoryLabel={categoryText}
              locationLabel={vendor.landmark ?? labels.defaultLocation}
              avatar={vendor.logoUrl ? <VendorLogo logoUrl={vendor.logoUrl} /> : undefined}
              trust={
                vendor.preferredBadge ? "preferred" : vendor.verified ? "id_verified" : undefined
              }
              trustLabel={
                vendor.preferredBadge
                  ? labels.preferredBadge
                  : vendor.verified
                    ? verifiedLabel
                    : undefined
              }
              stats={[
                { label: labels.listings, value: String(vendor.listingCount) },
                { label: labels.reviews, value: ratingValue },
              ]}
              ctaLabel={labels.viewProfile}
            />
          </Link>
        );
      })}
    </div>
  );
}
