import type { ComponentType } from "react";

import { CATEGORY_ICON_MAP } from "./icon-hues";
import { IconTile } from "./icon-tile";
import {
  LcCalendar,
  LcCar,
  LcDumbbell,
  LcHeartPulse,
  LcLayoutGrid,
  LcPackage,
  LcShirt,
  LcSmartphone,
  LcSparkles,
  LcSofa,
  LcUtensils,
  LcWrench,
} from "./lucide-icons";

const ICON_BY_NAME: Record<string, ComponentType<{ className?: string; duotone?: boolean }>> = {
  sparkles: LcSparkles,
  "heart-pulse": LcHeartPulse,
  utensils: LcUtensils,
  dumbbell: LcDumbbell,
  sofa: LcSofa,
  car: LcCar,
  smartphone: LcSmartphone,
  shirt: LcShirt,
  wrench: LcWrench,
  calendar: LcCalendar,
  package: LcPackage,
  "layout-grid": LcLayoutGrid,
};

export type CategoryIconProps = {
  categorySlug: string;
  size?: 32 | 40 | 48 | 56;
  className?: string;
};

/** Maps a top-level category slug to a coloured IconTile + Lucide icon. */
export function CategoryIcon({ categorySlug, size = 40, className }: CategoryIconProps) {
  const entry = CATEGORY_ICON_MAP[categorySlug] ?? CATEGORY_ICON_MAP.default!;
  const Icon = ICON_BY_NAME[entry.icon] ?? LcLayoutGrid;
  return (
    <IconTile hue={entry.hue} size={size} className={className}>
      <Icon className="size-5" duotone aria-hidden />
    </IconTile>
  );
}
