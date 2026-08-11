"use client";

import { BottomNav, type BottomNavItem } from "@vergeo/ui/src/bottom-nav";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMerchPreviewToken, withMerchPreviewParam } from "./merch-preview-nav";
import { useBusinessEligibility } from "./use-business-eligibility";

type BottomNavClientProps = {
  /** Items without `active` — the active tab is derived from the current route. */
  items: Array<Omit<BottomNavItem, "active">>;
  ariaLabel: string;
  locale: string;
  /**
   * Optional wholesale Supplies tab, appended only for verified business buyers
   * (eligibility resolved client-side). Absent for everyone else, so the common
   * bottom nav is unchanged.
   */
  suppliesItem?: Omit<BottomNavItem, "active">;
};

function normalise(path: string): string {
  const pathOnly = path.split(/[?#]/, 1)[0] ?? path;
  return pathOnly.replace(/\/+$/, "") || "/";
}

function routeSuffix(pathname: string, locale: string): string {
  const current = normalise(pathname);
  const localeRoot = normalise(`/${locale}`);
  if (current === localeRoot) {
    return "/";
  }
  return current.startsWith(`${localeRoot}/`) ? current.slice(localeRoot.length) : current;
}

function isWithinRoute(suffix: string, route: string): boolean {
  return suffix === route || suffix.startsWith(`${route}/`);
}

/** Resolve the buyer-facing tab for each storefront route family. */
export function isShopBottomNavItemActive(key: string, pathname: string, locale: string): boolean {
  const suffix = routeSuffix(pathname, locale);

  switch (key) {
    case "home":
      return suffix === "/";
    case "browse":
      return ["/search", "/categories", "/c", "/p", "/compare", "/supplies"].some((route) =>
        isWithinRoute(suffix, route),
      );
    case "ask":
      return isWithinRoute(suffix, "/ask");
    case "orders":
      return isWithinRoute(suffix, "/account/orders");
    case "account":
      return isWithinRoute(suffix, "/account") && !isWithinRoute(suffix, "/account/orders");
    case "supplies":
      return isWithinRoute(suffix, "/supplies");
    default:
      return false;
  }
}

/**
 * Route-aware bottom navigation. `ShopLayout` is a server component and cannot
 * read the pathname, so it delegates active-state resolution here. Exactly one
 * tab (at most) is marked active. Product, category, search, and comparison
 * routes resolve to Browse; nested account routes resolve to Account except for
 * Orders. When the gated Supplies tab exists, it wins the deliberate Browse /
 * Supplies overlap because it is appended after the standard tabs.
 */
export function BottomNavClient({ items, ariaLabel, locale, suppliesItem }: BottomNavClientProps) {
  const pathname = usePathname();
  const previewToken = useMerchPreviewToken();
  const eligibleForSupplies = useBusinessEligibility();

  const navItems = suppliesItem && eligibleForSupplies ? [...items, suppliesItem] : items;
  const previewAwareItems = navItems.map((item) => ({
    ...item,
    href: withMerchPreviewParam(item.href, previewToken),
  }));

  let bestIndex = -1;
  navItems.forEach((item, index) => {
    if (isShopBottomNavItemActive(item.key, pathname ?? `/${locale}`, locale)) {
      bestIndex = index;
    }
  });

  const resolved: BottomNavItem[] = previewAwareItems.map((item, index) => ({
    ...item,
    active: index === bestIndex,
  }));

  return (
    <BottomNav
      items={resolved}
      ariaLabel={ariaLabel}
      LinkComponent={Link}
      desktopHiddenClassName="lg:hidden"
    />
  );
}
