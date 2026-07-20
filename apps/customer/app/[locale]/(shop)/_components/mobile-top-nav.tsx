"use client";

import { TopNav } from "@vergeo/ui/src/top-nav";
import Link from "next/link";
import { useEffect, type ComponentProps, type ReactNode } from "react";

import { getCartItemCount, useCartActions, useCartStore } from "./cart/mini-cart-drawer";

type MobileTopNavProps = {
  locale: string;
  logo: ReactNode;
  searchSlot: ReactNode;
  /** Optional utility slot (theme control relocated to Account → Preferences). */
  actions?: ReactNode;
  cartIcon: ReactNode;
  cartLabel: string;
  skipLinkTargetId: string;
  skipLinkLabel: string;
  navAriaLabel: string;
  condensed?: boolean;
};

/**
 * Mobile TopNav with a live cart badge.
 *
 * Shop layout is a Server Component, so cart count must be resolved client-side
 * from the shared mini-cart store (refreshed once on mount).
 */
export function MobileTopNav({
  locale,
  logo,
  searchSlot,
  actions,
  cartIcon,
  cartLabel,
  skipLinkTargetId,
  skipLinkLabel,
  navAriaLabel,
  condensed = true,
}: MobileTopNavProps) {
  const { cart } = useCartStore();
  const { refresh } = useCartActions();

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const cartCount = getCartItemCount(cart);
  const topNavProps: ComponentProps<typeof TopNav> = {
    className: "lg:hidden",
    logo,
    searchSlot,
    actions,
    cartIcon,
    cartCount,
    cartHref: `/${locale}/cart`,
    cartLabel,
    skipLinkTargetId,
    skipLinkLabel,
    navAriaLabel,
    LinkComponent: Link,
    condensed,
  };

  return <TopNav {...topNavProps} />;
}
