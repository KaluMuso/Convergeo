"use client";

import { BottomNav, type BottomNavItem } from "@vergeo/ui/src/bottom-nav";
import Link from "next/link";
import { usePathname } from "next/navigation";

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
  return path.replace(/\/+$/, "") || "/";
}

/**
 * Route-aware bottom navigation. `ShopLayout` is a server component and cannot
 * read the pathname, so it delegates active-state resolution here. Exactly one
 * tab (at most) is marked active: the item whose href is the longest prefix of
 * the current path. Home matches only on an exact path (so it doesn't stay lit
 * on every nested route); ties are broken in favour of the later item.
 */
export function BottomNavClient({ items, ariaLabel, locale, suppliesItem }: BottomNavClientProps) {
  const pathname = usePathname();
  const eligibleForSupplies = useBusinessEligibility();
  const current = normalise(pathname ?? `/${locale}`);
  const home = normalise(`/${locale}`);

  const navItems = suppliesItem && eligibleForSupplies ? [...items, suppliesItem] : items;

  let bestIndex = -1;
  let bestLength = -1;
  navItems.forEach((item, index) => {
    const href = normalise(item.href);
    const matches =
      href === home ? current === home : current === href || current.startsWith(`${href}/`);
    if (matches && href.length >= bestLength) {
      bestLength = href.length;
      bestIndex = index;
    }
  });

  const resolved: BottomNavItem[] = navItems.map((item, index) => ({
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
