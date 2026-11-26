"use client";

import { IconTile } from "@vergeo/ui/src/icon-tile";
import {
  LcAlertTriangle,
  LcBanknote,
  LcBox,
  LcCalendar,
  LcClipboardList,
  LcGift,
  LcHome,
  LcImage,
  LcLayoutGrid,
  LcMessageCircle,
  LcPackage,
  LcSettings,
  LcShieldCheck,
  LcShoppingBag,
  LcSparkles,
  LcStore,
  LcTag,
  LcTicket,
  LcTrendingUp,
  LcTruck,
  LcUsers,
  LcWrench,
} from "@vergeo/ui/src/lucide-icons";

import type { AdminNavItemKey } from "./admin-nav-config";
import type { IconHue } from "@vergeo/ui/src/icon-hues";
import type { ComponentType } from "react";

type NavIconEntry = {
  hue: IconHue;
  Icon: ComponentType<{ className?: string; duotone?: boolean }>;
};

const NAV_ICON_MAP: Record<AdminNavItemKey, NavIconEntry> = {
  home: { hue: "blue", Icon: LcHome },
  analytics: { hue: "purple", Icon: LcTrendingUp },
  kyc: { hue: "teal", Icon: LcShieldCheck },
  branches: { hue: "cyan", Icon: LcStore },
  moderation: { hue: "orange", Icon: LcAlertTriangle },
  catalog: { hue: "green", Icon: LcLayoutGrid },
  disputes: { hue: "red", Icon: LcMessageCircle },
  support: { hue: "pink", Icon: LcUsers },
  intake: { hue: "green", Icon: LcMessageCircle },
  orders: { hue: "blue", Icon: LcShoppingBag },
  business: { hue: "slate", Icon: LcBanknote },
  merch: { hue: "amber", Icon: LcGift },
  homeFeed: { hue: "cyan", Icon: LcLayoutGrid },
  advertising: { hue: "orange", Icon: LcSparkles },
  offers: { hue: "pink", Icon: LcTag },
  clips: { hue: "purple", Icon: LcImage },
  events: { hue: "amber", Icon: LcCalendar },
  config: { hue: "slate", Icon: LcSettings },
  translations: { hue: "teal", Icon: LcClipboardList },
  theme: { hue: "purple", Icon: LcWrench },
  roles: { hue: "red", Icon: LcUsers },
  accounts: { hue: "blue", Icon: LcUsers },
  auditLog: { hue: "slate", Icon: LcClipboardList },
  services: { hue: "teal", Icon: LcWrench },
  inventory: { hue: "green", Icon: LcBox },
  coupons: { hue: "amber", Icon: LcTicket },
  extras: { hue: "cyan", Icon: LcPackage },
  trials: { hue: "pink", Icon: LcGift },
};

type AdminNavIconProps = {
  itemKey: AdminNavItemKey;
  size?: 32 | 40;
  className?: string;
};

export function AdminNavIcon({ itemKey, size = 32, className }: AdminNavIconProps) {
  const entry = NAV_ICON_MAP[itemKey] ?? { hue: "slate" as IconHue, Icon: LcTruck };
  const { hue, Icon } = entry;
  return (
    <IconTile hue={hue} size={size} className={className} aria-hidden>
      <Icon className={size === 32 ? "size-4" : "size-5"} duotone />
    </IconTile>
  );
}
