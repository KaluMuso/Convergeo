"use client";

import { BottomNav, type BottomNavItem, type BottomNavLinkProps } from "@vergeo/ui/src/bottom-nav";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { openMobileMenu, preloadMobileDrawer } from "./mega-menu/menu-events";
import { useMerchPreviewToken, withMerchPreviewParam } from "./merch-preview-nav";

type BottomNavClientProps = {
  /** Items without `active` — the active tab is derived from the current route. */
  items: Array<Omit<BottomNavItem, "active">>;
  ariaLabel: string;
  locale: string;
};

function isBrowseHref(href: string): boolean {
  return (href.split(/[?#]/, 1)[0] ?? href).endsWith("/search");
}

/**
 * The "Browse" tab opens the department drawer (drill-down mega menu). It stays
 * a real link to /search, so without JS (or with a modified click) it still
 * navigates to search.
 */
function ShopBottomNavLink({ href, children, ...rest }: BottomNavLinkProps) {
  if (!isBrowseHref(href)) {
    return (
      <Link href={href} {...rest}>
        {children}
      </Link>
    );
  }
  return (
    <Link
      href={href}
      {...rest}
      aria-haspopup="dialog"
      onPointerDown={preloadMobileDrawer}
      onClick={(event) => {
        if (
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey ||
          event.button !== 0
        ) {
          return;
        }
        event.preventDefault();
        openMobileMenu();
      }}
    >
      {children}
    </Link>
  );
}

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

/** Checkout and cart own the full viewport; hide the shop tab bar there. */
export function shouldRenderShopBottomNav(pathname: string, locale: string): boolean {
  const suffix = routeSuffix(pathname, locale);
  return !isWithinRoute(suffix, "/cart") && !isWithinRoute(suffix, "/checkout");
}

/** Resolve the buyer-facing tab for each storefront route family. */
export function isShopBottomNavItemActive(key: string, pathname: string, locale: string): boolean {
  const suffix = routeSuffix(pathname, locale);

  switch (key) {
    case "home":
      return suffix === "/";
    case "browse":
      return ["/search", "/categories", "/c", "/p", "/compare"].some((route) =>
        isWithinRoute(suffix, route),
      );
    case "ask":
      return isWithinRoute(suffix, "/ask");
    case "orders":
      return isWithinRoute(suffix, "/account/orders");
    case "account":
      return isWithinRoute(suffix, "/account") && !isWithinRoute(suffix, "/account/orders");
    default:
      return false;
  }
}

/**
 * Route-aware bottom navigation. `ShopLayout` is a server component and cannot
 * read the pathname, so it delegates active-state resolution here. Exactly one
 * tab (at most) is marked active. Product, category, search, and comparison
 * routes resolve to Browse; nested account routes resolve to Account except for
 * Orders.
 */
export function BottomNavClient({ items, ariaLabel, locale }: BottomNavClientProps) {
  const pathname = usePathname();
  const resolvedPath = pathname ?? `/${locale}`;
  if (!shouldRenderShopBottomNav(resolvedPath, locale)) {
    return null;
  }
  const previewToken = useMerchPreviewToken();
  const previewAwareItems = items.map((item) => ({
    ...item,
    href: withMerchPreviewParam(item.href, previewToken),
  }));

  let bestIndex = -1;
  items.forEach((item, index) => {
    if (isShopBottomNavItemActive(item.key, resolvedPath, locale)) {
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
      LinkComponent={ShopBottomNavLink}
      desktopHiddenClassName="lg:hidden"
    />
  );
}
