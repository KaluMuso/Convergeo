"use client";

import { AppHeader } from "@vergeo/ui/src/app-header";
import { IconSearch } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { useEffect } from "react";

import { getCartItemCount, useCartActions, useCartStore } from "./cart/mini-cart-drawer";
import { CategoryMegaMenu } from "./category-mega-menu";
import { DesktopHeaderSearch } from "./desktop-header-search";
import { useBusinessEligibility } from "./use-business-eligibility";

import type { SearchInputLabels } from "./search/search-input";

export type ShopHeaderLabels = {
  appName: string;
  skipToContent: string;
  navAriaLabel: string;
  desktopAriaLabel: string;
  searchPlaceholder: string;
  searchSubmit: string;
  allCategories: string;
  categoriesPanelAria: string;
  categoriesLoading: string;
  categoriesEmpty: string;
  viewAllCategories: string;
  featuredTitle: string;
  featuredPromo: string;
  featuredPromoCta: string;
  directory: string;
  services: string;
  events: string;
  askVergeo: string;
  supplies: string;
  account: string;
  cart: string;
  cartWithCount: string;
  searchInput: SearchInputLabels;
};

type ShopHeaderProps = {
  locale: string;
  labels: ShopHeaderLabels;
  localeSwitcher?: React.ReactNode;
};

const navLinkClassName =
  "inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing";

/**
 * Unified shop header (360→1440) — wraps AppHeader with cart, mega-menu, and
 * gated Supplies link for verified business buyers.
 */
export function ShopHeader({ locale, labels, localeSwitcher }: ShopHeaderProps) {
  const { cart } = useCartStore();
  const { refresh } = useCartActions();
  const eligibleForSupplies = useBusinessEligibility();

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const cartCount = getCartItemCount(cart);
  const cartCountLabel =
    cartCount > 0
      ? labels.cartWithCount.replace("{count}", String(cartCount > 99 ? 99 : cartCount))
      : undefined;

  const navLinks = [
    { key: "directory", href: `/${locale}/directory`, label: labels.directory },
    { key: "services", href: `/${locale}/services`, label: labels.services },
    { key: "events", href: `/${locale}/events`, label: labels.events },
    { key: "ask", href: `/${locale}/ask`, label: labels.askVergeo },
  ];

  const suppliesSlot = eligibleForSupplies ? (
    <li>
      <Link href={`/${locale}/supplies`} className={navLinkClassName}>
        {labels.supplies}
      </Link>
    </li>
  ) : null;

  return (
    <AppHeader
      variant="shop"
      data-testid="shop-header"
      appName={labels.appName}
      logoHref={`/${locale}`}
      mobileSearchSlot={
        <Link
          href={`/${locale}/search`}
          className="flex h-11 w-full max-w-md items-center gap-2 rounded-pill border border-border bg-surface px-4 text-sm text-text-3 transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          <IconSearch className="text-text-2" />
          <span className="truncate">{labels.searchPlaceholder}</span>
        </Link>
      }
      desktopSearchSlot={<DesktopHeaderSearch locale={locale} labels={labels.searchInput} />}
      categoriesSlot={
        <CategoryMegaMenu
          locale={locale}
          closeOnScroll
          labels={{
            trigger: labels.allCategories,
            panelAria: labels.categoriesPanelAria,
            loading: labels.categoriesLoading,
            empty: labels.categoriesEmpty,
            viewAll: labels.viewAllCategories,
            featuredTitle: labels.featuredTitle,
            featuredPromo: labels.featuredPromo,
            featuredPromoCta: labels.featuredPromoCta,
          }}
        />
      }
      navLinks={navLinks}
      suppliesSlot={suppliesSlot}
      localeSwitcher={localeSwitcher}
      cartCount={cartCount}
      cartHref={`/${locale}/cart`}
      cartLabel={labels.cart}
      cartCountLabel={cartCountLabel}
      accountLabel={labels.account}
      accountHref={`/${locale}/account`}
      skipLinkTargetId="shop-main"
      skipLinkLabel={labels.skipToContent}
      navAriaLabel={labels.navAriaLabel}
      desktopNavAriaLabel={labels.desktopAriaLabel}
      LinkComponent={Link}
    />
  );
}
