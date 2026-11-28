import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";

import type { CategoryBannerContent } from "./category-presentation";

type CategoryBannerProps = {
  banner: CategoryBannerContent;
};

/**
 * Admin-set banner at the top of a category page (RSC, no client JS). The image
 * is decorative (the title carries the meaning), and is the page's LCP candidate,
 * so it loads eagerly with a reserved 3:1 box to avoid layout shift.
 */
export function CategoryBanner({ banner }: CategoryBannerProps) {
  return (
    <section
      className="overflow-hidden rounded-lg border border-border bg-surface"
      data-testid="category-banner"
      aria-label={banner.title ?? undefined}
    >
      {banner.imagePublicId ? (
        <div className="relative aspect-[3/1] w-full bg-bg" data-testid="category-banner-image">
          <CloudinaryImageStatic
            publicId={banner.imagePublicId}
            alt=""
            width={1280}
            ratio="3/1"
            sizes="(max-width: 1280px) 100vw, 1280px"
            priority
            className="h-full w-full object-cover"
          />
        </div>
      ) : null}
      {banner.title ? (
        <div className="flex flex-col gap-1 px-4 py-3">
          <p className="font-display text-h3 font-bold text-display-ink">{banner.title}</p>
          {banner.description ? <p className="text-sm text-text-2">{banner.description}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
