"use client";

import Link from "next/link";
import { useState } from "react";

import { IconGridAll } from "./menu-icons";
import { tileInitial, tileTint } from "./nav-model";

type MenuTileProps = {
  href: string;
  label: string;
  /** "all" renders the View-all glyph instead of an initial. */
  kind?: "category" | "all";
  seed?: string;
  /** Admin-managed category image (Cloudinary URL); falls back to the initial tile. */
  imageUrl?: string | null;
  imageAlt?: string | null;
  /** Overrides the visible label for assistive tech (e.g. "View all in Fashion"). */
  ariaLabel?: string;
  onNavigate: () => void;
};

/**
 * Alibaba-style round tile — the single place a menu category image is rendered. With an
 * admin-managed `imageUrl` it shows the (lazy, sized) image; otherwise, or if the image
 * fails to load, the tokenised initial placeholder.
 */
export function MenuTile({
  href,
  label,
  kind = "category",
  seed,
  imageUrl,
  imageAlt,
  ariaLabel,
  onNavigate,
}: MenuTileProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = kind === "category" && Boolean(imageUrl) && !imageFailed;
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-label={ariaLabel}
      data-menu-tile
      className="group flex min-w-0 flex-col items-center gap-2 rounded-lg p-1 text-center focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <span
        aria-hidden={showImage && imageAlt ? undefined : "true"}
        className="grid size-16 place-items-center overflow-hidden rounded-full border border-border font-display text-h3 font-bold text-display-ink transition-transform duration-fast ease-std group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        style={{
          backgroundColor: kind === "all" ? "var(--bg-2)" : tileTint(seed ?? label),
        }}
      >
        {showImage ? (
          <img
            src={imageUrl ?? undefined}
            alt={imageAlt ?? ""}
            width={64}
            height={64}
            loading="lazy"
            decoding="async"
            data-menu-tile-image
            className="size-full object-cover"
            onError={() => setImageFailed(true)}
          />
        ) : kind === "all" ? (
          <IconGridAll className="size-6 text-primary" />
        ) : (
          tileInitial(label)
        )}
      </span>
      <span className="line-clamp-2 w-full break-words text-xs font-medium text-text group-hover:text-primary">
        {label}
      </span>
    </Link>
  );
}
