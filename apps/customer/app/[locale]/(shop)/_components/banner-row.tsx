import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import Link from "next/link";

import type { MerchSlotRow } from "./merch-data";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type BannerItem = {
  key: string;
  title: string;
  subtitle?: string;
  href: string;
  imagePublicId?: string;
  tag?: string;
};

function parseBannerItems(payload: Record<string, unknown>, locale: string): BannerItem[] {
  const rawItems = payload.items;
  if (!Array.isArray(rawItems)) {
    return [];
  }

  return rawItems.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }

    const record = entry as Record<string, unknown>;
    const title = typeof record.title === "string" ? record.title : undefined;
    const href = typeof record.href === "string" ? record.href : `/${locale}/search`;

    if (!title) {
      return [];
    }

    return [
      {
        key: typeof record.key === "string" ? record.key : `banner-${index}`,
        title,
        subtitle: typeof record.subtitle === "string" ? record.subtitle : undefined,
        href,
        imagePublicId:
          typeof record.image_public_id === "string" ? record.image_public_id : undefined,
        tag: typeof record.tag === "string" ? record.tag : undefined,
      },
    ];
  });
}

type BannerRowProps = {
  slot?: MerchSlotRow;
  locale: string;
  t: CatalogTranslator;
};

export function BannerRow({ slot, locale, t }: BannerRowProps) {
  const items = slot ? parseBannerItems(slot.payload, locale) : [];

  if (items.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="home-banner-heading" className="flex flex-col gap-3">
      <h2 id="home-banner-heading" className="font-display text-h2 text-display-ink">
        {t("home.bannerRow.title")}
      </h2>
      <ul className="grid list-none gap-3 p-0">
        {items.map((item) => (
          <li key={item.key}>
            <Link
              href={item.href}
              className="flex min-h-11 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1"
            >
              {item.imagePublicId ? (
                <CloudinaryImageStatic
                  publicId={item.imagePublicId}
                  alt={item.title}
                  width={720}
                  ratio="21/9"
                />
              ) : null}
              <div className="flex flex-col gap-1 p-3">
                {item.tag ? (
                  <span className="text-micro font-semibold uppercase tracking-wide text-accent">
                    {item.tag}
                  </span>
                ) : null}
                <span className="text-h3 font-semibold text-text">{item.title}</span>
                {item.subtitle ? (
                  <span className="text-sm text-text-2">{item.subtitle}</span>
                ) : null}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
