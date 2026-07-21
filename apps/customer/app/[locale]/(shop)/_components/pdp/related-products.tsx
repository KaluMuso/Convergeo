import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";

export type RelatedProductItem = {
  slug: string;
  name: string;
  image_public_id: string | null;
  from_price_ngwee: number | null;
};

export type RelatedProductsLabels = {
  heading: string;
  vendorFallback: string;
  noReviews: string;
  reviewCount: string;
  /** Required by ProductCard a11y types; handlers omitted so actions stay unwired. */
  quickAdd: string;
  wishlist: string;
  mediaEmpty: string;
};

type RelatedProductsProps = {
  locale: string;
  items: RelatedProductItem[];
  labels: RelatedProductsLabels;
  cloudName?: string;
};

function RelatedMedia({
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
        className="flex h-full w-full items-center justify-center bg-bg-2 text-sm text-text-2"
        role="img"
        aria-label={emptyLabel}
      />
    );
  }
  return (
    <CloudinaryImageStatic
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
 * Related rail using the shared ProductCard when a real from-price exists.
 * Items without a price render a media+title card — never a fabricated K0.00.
 */
export function RelatedProducts({ locale, items, labels, cloudName }: RelatedProductsProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="pdp-related-heading"
      className="flex flex-col gap-3"
      data-testid="pdp-related"
    >
      <h2 id="pdp-related-heading" className="font-display text-lg font-semibold text-text">
        {labels.heading}
      </h2>
      <ul className="m-0 grid list-none grid-cols-2 gap-3 p-0 md:grid-cols-3 lg:grid-cols-4">
        {items.map((item) => (
          <li key={item.slug} className="min-w-0">
            <Link href={`/${locale}/p/${item.slug}`} className="block min-w-0 no-underline">
              {item.from_price_ngwee !== null ? (
                <ProductCard
                  title={item.name}
                  vendorLabel={labels.vendorFallback}
                  ngwee={item.from_price_ngwee}
                  rating={0}
                  reviewCount={0}
                  noReviewsLabel={labels.noReviews}
                  reviewCountLabel={labels.reviewCount}
                  quickAddLabel={labels.quickAdd}
                  wishlistLabel={labels.wishlist}
                  mediaEmptyLabel={labels.mediaEmpty}
                  media={
                    <RelatedMedia
                      publicId={item.image_public_id}
                      alt={item.name}
                      cloudName={cloudName}
                      emptyLabel={labels.mediaEmpty}
                    />
                  }
                />
              ) : (
                <article
                  className="card-lift flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1"
                  data-testid="pdp-related-unpriced"
                >
                  <div className="aspect-[4/3] bg-bg-2">
                    <RelatedMedia
                      publicId={item.image_public_id}
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
