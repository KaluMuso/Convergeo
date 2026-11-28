"use client";

import Link from "next/link";

import { IconGridAll } from "./menu-icons";
import { tileInitial, tileTint } from "./nav-model";

type MenuTileProps = {
  href: string;
  label: string;
  /** "all" renders the View-all glyph instead of an initial. */
  kind?: "category" | "all";
  seed?: string;
  /** Overrides the visible label for assistive tech (e.g. "View all in Fashion"). */
  ariaLabel?: string;
  onNavigate: () => void;
};

/**
 * Alibaba-style round tile. Categories have no image field today (and no DB
 * migration is allowed here), so the tile is a tokenised initial placeholder;
 * swap the inner node for an <img> when an image field lands.
 */
export function MenuTile({
  href,
  label,
  kind = "category",
  seed,
  ariaLabel,
  onNavigate,
}: MenuTileProps) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-label={ariaLabel}
      data-menu-tile
      className="group flex min-w-0 flex-col items-center gap-2 rounded-lg p-1 text-center focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <span
        aria-hidden="true"
        className="grid size-16 place-items-center rounded-full border border-border font-display text-h3 font-bold text-display-ink transition-transform duration-fast ease-std group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        style={{
          backgroundColor: kind === "all" ? "var(--bg-2)" : tileTint(seed ?? label),
        }}
      >
        {kind === "all" ? <IconGridAll className="size-6 text-primary" /> : tileInitial(label)}
      </span>
      <span className="line-clamp-2 w-full break-words text-xs font-medium text-text group-hover:text-primary">
        {label}
      </span>
    </Link>
  );
}
