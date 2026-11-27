import type { AdminNavCapabilities } from "../../../lib/admin-nav-capabilities";

export type AdminNavItemKey =
  | "home"
  | "analytics"
  | "kyc"
  | "branches"
  | "moderation"
  | "catalog"
  | "disputes"
  | "support"
  | "intake"
  | "orders"
  | "dispatch"
  | "business"
  | "merch"
  | "homeFeed"
  | "advertising"
  | "offers"
  | "clips"
  | "events"
  | "config"
  | "translations"
  | "theme"
  | "roles"
  | "accounts"
  | "auditLog"
  | "services"
  | "inventory"
  | "coupons"
  | "extras"
  | "trials";

export type AdminNavGroupKey = "overview" | "trust" | "commerce" | "platform";

export type AdminNavItem = {
  key: AdminNavItemKey;
  href: string;
};

export type AdminNavGroup = {
  key: AdminNavGroupKey;
  items: AdminNavItem[];
};

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    key: "overview",
    items: [
      { key: "home", href: "" },
      { key: "analytics", href: "analytics" },
    ],
  },
  {
    key: "trust",
    items: [
      { key: "kyc", href: "kyc" },
      { key: "branches", href: "branches" },
      { key: "moderation", href: "moderation" },
      { key: "catalog", href: "catalog" },
      { key: "disputes", href: "disputes" },
      { key: "support", href: "support" },
      { key: "intake", href: "intake" },
      { key: "events", href: "events" },
    ],
  },
  {
    key: "commerce",
    items: [
      { key: "orders", href: "orders" },
      { key: "dispatch", href: "orders/dispatch" },
      { key: "business", href: "business" },
      { key: "merch", href: "merch" },
      { key: "homeFeed", href: "home-feed" },
      { key: "advertising", href: "advertising" },
      { key: "offers", href: "offers" },
      { key: "clips", href: "clips" },
      { key: "services", href: "services" },
      { key: "inventory", href: "inventory" },
      { key: "coupons", href: "coupons" },
      { key: "extras", href: "extras" },
      { key: "trials", href: "trials" },
    ],
  },
  {
    key: "platform",
    items: [
      { key: "config", href: "config" },
      { key: "translations", href: "translations" },
      { key: "theme", href: "theme" },
      { key: "roles", href: "roles" },
      { key: "accounts", href: "accounts" },
      { key: "auditLog", href: "audit-log" },
    ],
  },
];

export function filterAdminNavGroups(
  capabilities: AdminNavCapabilities,
  groups: AdminNavGroup[] = ADMIN_NAV_GROUPS,
): AdminNavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => capabilities[item.key]),
    }))
    .filter((group) => group.items.length > 0);
}

export function flattenAdminNavItems(groups: AdminNavGroup[]): AdminNavItem[] {
  return groups.flatMap((group) => group.items);
}

export function adminItemHref(locale: string, href: string): string {
  return href ? `/${locale}/${href}` : `/${locale}`;
}

export function resolveAdminActiveItem(
  pathRest: string,
  items: AdminNavItem[] = flattenAdminNavItems(ADMIN_NAV_GROUPS),
): AdminNavItemKey | undefined {
  const rest = pathRest === "/" ? "/" : pathRest.replace(/\/+$/, "");

  let best: AdminNavItem | undefined;
  let bestLen = -1;

  for (const item of items) {
    const pattern = item.href ? `/${item.href}` : "/";
    const matches =
      pattern === "/" ? rest === "/" : rest === pattern || rest.startsWith(`${pattern}/`);
    if (matches && pattern.length >= bestLen) {
      best = item;
      bestLen = pattern.length;
    }
  }

  return best?.key;
}

export function resolveAdminActiveGroup(
  pathRest: string,
  groups: AdminNavGroup[] = ADMIN_NAV_GROUPS,
): AdminNavGroupKey | undefined {
  const active = resolveAdminActiveItem(pathRest, flattenAdminNavItems(groups));
  if (!active) {
    return undefined;
  }
  return groups.find((group) => group.items.some((item) => item.key === active))?.key;
}

/**
 * Order detail (`/orders/<id>`) is readable by finance roles (`orders`) and by logistics
 * operators (`dispatch`), because the API grants `GET /admin/orders/{id}` to both. The
 * search page (`/orders`) and every other route keep their single nav item's permission.
 */
export function adminRouteAllowedByAlternateItem(
  pathRest: string,
  capabilities: AdminNavCapabilities,
): boolean {
  const rest = pathRest.replace(/\/+$/, "");
  return (
    /^\/orders\/(?!dispatch$)[^/]+$/.test(rest) && (capabilities.orders || capabilities.dispatch)
  );
}
