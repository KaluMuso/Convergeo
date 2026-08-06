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

/** Primary mobile bottom-nav destinations (fourth opens the full menu). */
export const VENDOR_MOBILE_PRIMARY: VendorMobilePrimaryKey[] = [
  "home",
  "orders",
  "listings",
  VENDOR_MORE_MENU_KEY,
];

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

const ALL_ITEMS = VENDOR_NAV_GROUPS.flatMap((group) => group.items);

export function vendorItemHref(locale: string, href: string): string {
  return href ? `/${locale}${href}` : `/${locale}`;
}

/** Longest-prefix match for active nav highlighting. */
export function resolveVendorActiveItem(pathRest: string): VendorNavItemKey | undefined {
  const rest = pathRest === "/" ? "/" : pathRest.replace(/\/+$/, "");

  let best: VendorNavItem | undefined;
  let bestLen = -1;

  for (const item of ALL_ITEMS) {
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

const MOBILE_TAB_KEYS = new Set<VendorNavItemKey>(["home", "orders", "listings"]);

export function isVendorMoreMenuActive(pathRest: string): boolean {
  const active = resolveVendorActiveItem(pathRest);
  if (!active) {
    return false;
  }
  return !MOBILE_TAB_KEYS.has(active);
}
