export type AdminNavItemKey =
  | "home"
  | "kyc"
  | "moderation"
  | "disputes"
  | "support"
  | "intake"
  | "orders"
  | "business"
  | "merch"
  | "clips"
  | "config"
  | "translations"
  | "theme";

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
    items: [{ key: "home", href: "" }],
  },
  {
    key: "trust",
    items: [
      { key: "kyc", href: "kyc" },
      { key: "moderation", href: "moderation" },
      { key: "disputes", href: "disputes" },
      { key: "support", href: "support" },
      { key: "intake", href: "intake" },
    ],
  },
  {
    key: "commerce",
    items: [
      { key: "orders", href: "orders" },
      { key: "business", href: "business" },
      { key: "merch", href: "merch" },
      { key: "clips", href: "clips" },
    ],
  },
  {
    key: "platform",
    items: [
      { key: "config", href: "config" },
      { key: "translations", href: "translations" },
      { key: "theme", href: "theme" },
    ],
  },
];

const ALL_ITEMS = ADMIN_NAV_GROUPS.flatMap((group) => group.items);

export function adminItemHref(locale: string, href: string): string {
  return href ? `/${locale}/${href}` : `/${locale}`;
}

export function resolveAdminActiveItem(pathRest: string): AdminNavItemKey | undefined {
  const rest = pathRest === "/" ? "/" : pathRest.replace(/\/+$/, "");

  let best: AdminNavItem | undefined;
  let bestLen = -1;

  for (const item of ALL_ITEMS) {
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

export function resolveAdminActiveGroup(pathRest: string): AdminNavGroupKey | undefined {
  const active = resolveAdminActiveItem(pathRest);
  if (!active) {
    return undefined;
  }
  return ADMIN_NAV_GROUPS.find((group) => group.items.some((item) => item.key === active))?.key;
}
