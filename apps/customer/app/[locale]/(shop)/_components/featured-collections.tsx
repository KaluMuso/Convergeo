import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import { ProductCard } from "@vergeo/ui/src/product-card";
import Link from "next/link";

import type { MerchSlotRow } from "./merch-data";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type CollectionItem = {
  key: string;
  title: string;
  href: string;
  imagePublicId?: string;
  ngwee: number;
  vendorLabel: string;
};

type CollectionGroup = {
  key: string;
  title: string;
  items: CollectionItem[];
};

function parseCollections(payload: Record<string, unknown>, locale: string): CollectionGroup[] {
  const rawCollections = payload.collections;
  if (!Array.isArray(rawCollections)) {
    return [];
  }

  return rawCollections.flatMap((entry, collectionIndex) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }

    const record = entry as Record<string, unknown>;
    const title =
      typeof record.title === "string"
        ? record.title
        : typeof record.title_key === "string"
          ? record.title_key
          : undefined;

    if (!title) {
      return [];
    }

    const rawItems = record.items;
    const items = Array.isArray(rawItems)
      ? rawItems.flatMap((itemEntry, itemIndex) => {
          if (!itemEntry || typeof itemEntry !== "object") {
            return [];
          }

          const item = itemEntry as Record<string, unknown>;
          const itemTitle = typeof item.title === "string" ? item.title : undefined;
          if (!itemTitle) {
            return [];
          }

          return [
            {
              key:
                typeof item.key === "string"
                  ? item.key
                  : `collection-${collectionIndex}-item-${itemIndex}`,
              title: itemTitle,
              href: typeof item.href === "string" ? item.href : `/${locale}/search`,
              imagePublicId:
                typeof item.image_public_id === "string" ? item.image_public_id : undefined,
              ngwee: typeof item.ngwee === "number" ? item.ngwee : 0,
              vendorLabel:
                typeof item.vendor_label === "string" ? item.vendor_label : "Vergeo5 vendor",
            },
          ];
        })
      : [];

    return [
      {
        key: typeof record.key === "string" ? record.key : `collection-${collectionIndex}`,
        title,
        items,
      },
    ];
  });
}

type FeaturedCollectionsProps = {
  slot?: MerchSlotRow;
  locale: string;
  t: CatalogTranslator;
};

export function FeaturedCollections({ slot, locale, t }: FeaturedCollectionsProps) {
  const collections = slot ? parseCollections(slot.payload, locale) : [];

  if (collections.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="home-featured-heading" className="flex flex-col gap-4">
      <h2 id="home-featured-heading" className="font-display text-h2 text-display-ink">
        {t("home.featured.title")}
      </h2>
      {collections.map((collection) => (
        <div key={collection.key} className="flex flex-col gap-3">
          <h3 className="text-h3 font-semibold text-text">{collection.title}</h3>
          {collection.items.length > 0 ? (
            <ul className="grid list-none grid-cols-2 gap-2 p-0 sm:gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {collection.items.map((item) => (
                <li key={item.key}>
                  <Link href={item.href} className="block">
                    <ProductCard
                      title={item.title}
                      vendorLabel={item.vendorLabel}
                      ngwee={item.ngwee}
                      rating={0}
                      reviewCount={0}
                      noReviewsLabel={t("home.featured.noReviews")}
                      quickAddLabel={t("home.featured.quickAdd")}
                      wishlistLabel={t("home.featured.wishlist")}
                      density="compact"
                      media={
                        item.imagePublicId ? (
                          <CloudinaryImageStatic
                            publicId={item.imagePublicId}
                            alt={item.title}
                            width={360}
                            ratio="4/3"
                          />
                        ) : undefined
                      }
                    />
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </section>
  );
}
