import type { ReactNode } from "react";

import { ICON_HUE_DARK, ICON_HUE_LIGHT, ICON_HUES, type IconHue } from "./icon-hues";

export type IconTileSize = 32 | 40 | 48 | 56;

export type IconTileProps = {
  hue: IconHue;
  size?: IconTileSize;
  /** Icon node — typically a Lucide icon with `duotone` styling. */
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
  /** Force light or dark hue tokens (default: follow `data-theme`). */
  mode?: "light" | "dark";
};

const SIZE_PX: Record<IconTileSize, number> = {
  32: 32,
  40: 40,
  48: 48,
  56: 56,
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Soft tinted square behind a coloured duotone icon (Google Business Profile style).
 */
export function IconTile({
  hue,
  size = 40,
  children,
  className,
  "data-testid": dataTestId,
  mode,
}: IconTileProps) {
  if (!ICON_HUES.includes(hue)) {
    throw new Error(`Unknown icon hue: ${hue}`);
  }

  const px = SIZE_PX[size];
  const tokens = mode === "dark" ? ICON_HUE_DARK[hue] : ICON_HUE_LIGHT[hue];

  return (
    <div
      data-testid={dataTestId ?? "icon-tile"}
      data-hue={hue}
      data-size={size}
      className={cx("inline-flex shrink-0 items-center justify-center rounded-xl", className)}
      style={{
        width: px,
        height: px,
        background: tokens.tileBg,
        color: tokens.stroke,
        ["--icon-tile-fill" as string]: tokens.fill,
      }}
    >
      {children}
    </div>
  );
}
