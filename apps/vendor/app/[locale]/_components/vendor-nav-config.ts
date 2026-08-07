import type { VendorNavCapabilities } from "../../../lib/nav-capabilities";

export type VendorNavItemKey =
  | "home"
  | "orders"
  | "listings"
  | "scan"
  | "returns"
  | "analytics"
  | "services"
  | "events"
  | "rfq"
  | "jobs"
  | "clips"
  | "reviews"
  | "profile"
  | "payouts"
  | "disputes"
  | "intake";

export type VendorNavGroupKey = "operate" | "sell" | "business";

export type VendorNavItem = {
  key: VendorNavItemKey;
  /** Path after locale prefix, e.g. `/orders`. */
  href: string;
};

export type VendorNavGroup = {
  key: VendorNavGroupKey;
  items: VendorNavItem[];
};

export const VENDOR_MORE_MENU_KEY = "more" as const;

export type VendorMobilePrimaryKey = VendorNavItemKey | typeof VENDOR_MORE_MENU_KEY;

/** Bottom-nav tabs that also appear in the mobile More sheet (duplicates avoided). */
export const VENDOR_MOBILE_TAB_KEYS = new Set<VendorNavItemKey>(["home", "orders", "listings"]);

/** Primary mobile bottom-nav destinations before capability filtering. */
export const VENDOR_MOBILE_PRIMARY_TEMPLATE: VendorNavItemKey[] = ["home", "orders", "listings"];

export const VENDOR_NAV_GROUPS: VendorNavGroup[] = [
  {
    key: "operate",
    items: [
      { key: "home", href: "" },
      { key: "orders", href: "/orders" },
      { key: "listings", href: "/listings" },
      { key: "scan", href: "/scan" },
      { key: "returns", href: "/returns" },
    ],
  },
  {
    key: "sell",
    items: [
      { key: "analytics", href: "/analytics" },
      { key: "services", href: "/services" },
      { key: "events", href: "/events" },
      { key: "rfq", href: "/rfq" },
      { key: "jobs", href: "/jobs" },
      { key: "clips", href: "/clips" },
      { key: "reviews", href: "/reviews" },
    ],
  },
  {
    key: "business",
    items: [
      { key: "profile", href: "/profile" },
      { key: "payouts", href: "/payouts" },
      { key: "disputes", href: "/disputes" },
      { key: "intake", href: "/intake" },
    ],
  },
];

export function filterVendorNavGroups(
  capabilities: VendorNavCapabilities,
  groups: VendorNavGroup[] = VENDOR_NAV_GROUPS,
): VendorNavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => capabilities[item.key]),
    }))
    .filter((group) => group.items.length > 0);
}

export function flattenVendorNavItems(groups: VendorNavGroup[]): VendorNavItem[] {
  return groups.flatMap((group) => group.items);
}

/** Items shown in the mobile More sheet (excludes primary bottom tabs). */
export function buildVendorMoreMenuGroups(groups: VendorNavGroup[]): VendorNavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !VENDOR_MOBILE_TAB_KEYS.has(item.key)),
    }))
    .filter((group) => group.items.length > 0);
}

/** Build mobile bottom-nav keys including More only when secondary items exist. */
export function buildVendorMobilePrimary(groups: VendorNavGroup[]): VendorMobilePrimaryKey[] {
  const visibleKeys = new Set(flattenVendorNavItems(groups).map((item) => item.key));
  const primary: VendorMobilePrimaryKey[] = [];

  for (const key of VENDOR_MOBILE_PRIMARY_TEMPLATE) {
    if (visibleKeys.has(key)) {
      primary.push(key);
    }
  }

  const moreItems = buildVendorMoreMenuGroups(groups).flatMap((group) => group.items);
  if (moreItems.length > 0) {
    primary.push(VENDOR_MORE_MENU_KEY);
  }

  return primary;
}

export function vendorItemHref(locale: string, href: string): string {
  return href ? `/${locale}${href}` : `/${locale}`;
}

/** Longest-prefix match for active nav highlighting against visible items. */
export function resolveVendorActiveItem(
  pathRest: string,
  items: VendorNavItem[] = flattenVendorNavItems(VENDOR_NAV_GROUPS),
): VendorNavItemKey | undefined {
  const rest = pathRest === "/" ? "/" : pathRest.replace(/\/+$/, "");

  let best: VendorNavItem | undefined;
  let bestLen = -1;

  for (const item of items) {
    const pattern = item.href || "/";
    const matches =
      pattern === "/" ? rest === "/" : rest === pattern || rest.startsWith(`${pattern}/`);
    if (matches && pattern.length >= bestLen) {
      best = item;
      bestLen = pattern.length;
    }
  }

  return best?.key;
}

export function isVendorMoreMenuActive(pathRest: string, groups: VendorNavGroup[]): boolean {
  const moreItems = buildVendorMoreMenuGroups(groups);
  const active = resolveVendorActiveItem(pathRest, flattenVendorNavItems(moreItems));
  return active !== undefined;
}
