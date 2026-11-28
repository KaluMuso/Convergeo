import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";

import { vibeStyle, type Archetype } from "../../_lib/archetypes";

import { ArchetypeIcon } from "./archetype-icon";

import type { ReactNode } from "react";

type ServiceHeroProps = {
  archetype: Archetype;
  archetypeLabel: string;
  title: string;
  area: string | null;
  priceLine: string;
  responseLine: string | null;
  badges: ReactNode;
  images: string[];
};

/**
 * Image-led hero for every service. Three or more photos form a mosaic, one or two a
 * single wide photo, none a coloured vibe banner with the archetype icon, so the page never
 * shows an empty half. Colours come from the archetype vibe (packages/ui icon hues).
 */
export function ServiceHero({
  archetype,
  archetypeLabel,
  title,
  area,
  priceLine,
  responseLine,
  badges,
  images,
}: ServiceHeroProps) {
  return (
    <header
      className="overflow-hidden rounded-lg border border-border bg-[var(--vibe-tint)] shadow-2"
      style={vibeStyle(archetype)}
      data-testid="service-hero"
      data-archetype={archetype}
    >
      {images.length >= 3 ? (
        <div
          className="grid h-64 grid-cols-3 grid-rows-2 gap-1 md:h-[22rem]"
          data-testid="service-hero-mosaic"
        >
          <div className="col-span-2 row-span-2">
            <CloudinaryImageStatic
              publicId={images[0] as string}
              alt={title}
              width={960}
              sizes="(max-width: 1024px) 66vw, 55vw"
              priority
              className="h-full w-full rounded-none"
            />
          </div>
          {images.slice(1, 3).map((id, index) => (
            <CloudinaryImageStatic
              key={id}
              publicId={id}
              alt={`${title} ${index + 2}`}
              width={480}
              sizes="(max-width: 1024px) 33vw, 25vw"
              className="h-full w-full rounded-none"
            />
          ))}
        </div>
      ) : images.length > 0 ? (
        <CloudinaryImageStatic
          publicId={images[0] as string}
          alt={title}
          width={1200}
          sizes="100vw"
          ratio="16/9"
          priority
          className="max-h-[22rem] w-full rounded-none"
        />
      ) : (
        <div
          className="flex h-28 items-center justify-center bg-gradient-to-br from-[var(--vibe-strong)] via-[var(--vibe-tint)] to-surface text-[var(--vibe)] md:h-36"
          data-testid="service-hero-banner"
        >
          <ArchetypeIcon archetype={archetype} className="h-14 w-14 md:h-16 md:w-16" />
        </div>
      )}
      <div className="flex flex-col gap-3 p-5 md:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex min-h-7 items-center gap-1.5 rounded-pill bg-[var(--vibe-strong)] px-3 text-xs font-semibold text-text">
            <ArchetypeIcon archetype={archetype} className="h-3.5 w-3.5" />
            {archetypeLabel}
          </span>
          {badges}
        </div>
        <h1 className="m-0 font-display text-hero text-display-ink">{title}</h1>
        {area ? <p className="m-0 text-sm text-text-2">{area}</p> : null}
        <p className="m-0 text-lg font-semibold text-text">{priceLine}</p>
        {responseLine ? (
          <p className="m-0 text-sm text-text-2" data-testid="service-response-time">
            {responseLine}
          </p>
        ) : null}
      </div>
    </header>
  );
}
