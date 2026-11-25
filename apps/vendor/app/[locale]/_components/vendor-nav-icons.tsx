import { IconTile, type IconTileSize } from "@vergeo/ui/src/icon-tile";
import {
  LcBanknote,
  LcCalendar,
  LcClipboardList,
  LcFileText,
  LcGift,
  LcHome,
  LcLayoutGrid,
  LcMessageCircle,
  LcPackage,
  LcRefreshCw,
  LcSettings,
  LcShield,
  LcSparkles,
  LcStar,
  LcStore,
  LcTag,
  LcTrendingUp,
  LcWallet,
  LcWrench,
  LcZap,
} from "@vergeo/ui/src/lucide-icons";

import type { VendorNavItemKey } from "./vendor-nav-config";
import type { IconHue } from "@vergeo/ui/src/icon-hues";
import type { ComponentType, ReactNode } from "react";

type NavIconSpec = {
  hue: IconHue;
  Icon: ComponentType<{ className?: string; duotone?: boolean }>;
};

const NAV_ICON_SPECS: Record<VendorNavItemKey, NavIconSpec> = {
  home: { hue: "blue", Icon: LcHome },
  orders: { hue: "orange", Icon: LcClipboardList },
  listings: { hue: "green", Icon: LcPackage },
  scan: { hue: "purple", Icon: LcZap },
  returns: { hue: "amber", Icon: LcRefreshCw },
  analytics: { hue: "teal", Icon: LcTrendingUp },
  offers: { hue: "pink", Icon: LcTag },
  services: { hue: "cyan", Icon: LcWrench },
  events: { hue: "purple", Icon: LcCalendar },
  rfq: { hue: "slate", Icon: LcFileText },
  jobs: { hue: "blue", Icon: LcClipboardList },
  clips: { hue: "pink", Icon: LcSparkles },
  reviews: { hue: "amber", Icon: LcStar },
  coupons: { hue: "green", Icon: LcGift },
  profile: { hue: "blue", Icon: LcStore },
  payouts: { hue: "teal", Icon: LcWallet },
  disputes: { hue: "red", Icon: LcShield },
  intake: { hue: "cyan", Icon: LcMessageCircle },
  settings: { hue: "slate", Icon: LcSettings },
  extras: { hue: "slate", Icon: LcLayoutGrid },
};

type VendorNavIconProps = {
  itemKey: VendorNavItemKey;
  size?: IconTileSize;
  className?: string;
};

export function VendorNavIcon({ itemKey, size = 32, className }: VendorNavIconProps) {
  const { Icon, hue } = NAV_ICON_SPECS[itemKey];
  const iconClass = size <= 32 ? "size-4" : "size-5";
  return (
    <IconTile hue={hue} size={size} className={className}>
      <Icon className={iconClass} duotone aria-hidden />
    </IconTile>
  );
}

export function VendorActionIcon({
  hue,
  children,
  size = 48,
}: {
  hue: IconHue;
  children: ReactNode;
  size?: IconTileSize;
}) {
  return (
    <IconTile hue={hue} size={size}>
      {children}
    </IconTile>
  );
}

export const VendorQuickActionIcons = {
  product: { hue: "green" as const, Icon: LcPackage },
  scan: { hue: "purple" as const, Icon: LcZap },
  orders: { hue: "orange" as const, Icon: LcClipboardList },
  payouts: { hue: "teal" as const, Icon: LcBanknote },
};
