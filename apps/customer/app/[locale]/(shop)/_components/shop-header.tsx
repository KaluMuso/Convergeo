"use client";

import { AppHeader } from "@vergeo/ui/src/app-header";
import { IconCart } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { useEffect, type ReactNode } from "react";

import { BrandLogo } from "./brand-logo";
import {
  CartNavTrigger,
  getCartItemCount,
  useCartActions,
  useCartStore,
} from "./cart/mini-cart-drawer";
import { CategoryMegaMenu } from "./category-mega-menu";
import { DesktopHeaderSearch } from "./desktop-header-search";
import { MerchPreviewLink, useMerchPreviewToken, withMerchPreviewParam } from "./merch-preview-nav";
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
  openCart: string;
  searchInput: SearchInputLabels;
};

type ShopHeaderProps = {
  locale: string;
  labels: ShopHeaderLabels;
  localeSwitcher?: React.ReactNode;
  /** Mobile search affordance — typically `MobileHeaderSearch` from the layout. */
  mobileSearchSlot?: ReactNode;
};

const navLinkClassName =
  "inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing";

/**
 * Unified shop header (360→1440) — wraps AppHeader with cart, mega-menu, and
 * gated Supplies link for verified business buyers.
 */
export function ShopHeader({ locale, labels, localeSwitcher, mobileSearchSlot }: ShopHeaderProps) {
  const previewToken = useMerchPreviewToken();
  const { cart } = useCartStore();
  const { refresh } = useCartActions();
  const eligibleForSupplies = useBusinessEligibility();

  useEffect(() => {
    // Defer cart hydration until after first paint so header mount does not
    // contend with LCP on home/checkout under Fast-3G CI budgets.
    let cancelled = false;
    const run = () => {
      if (!cancelled) {
        void refresh();
      }
    };
    const w = window as Window &
      typeof globalThis & {
        requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
        cancelIdleCallback?: (id: number) => void;
      };
    let idleId: number | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    if (typeof w.requestIdleCallback === "function") {
      idleId = w.requestIdleCallback(run, { timeout: 1500 });
    } else {
      timeoutId = setTimeout(run, 0);
    }
    return () => {
      cancelled = true;
      if (idleId !== undefined && typeof w.cancelIdleCallback === "function") {
        w.cancelIdleCallback(idleId);
      }
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    };
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
  ].map((link) => ({
    ...link,
    href: withMerchPreviewParam(link.href, previewToken),
  }));

  const suppliesSlot = eligibleForSupplies ? (
    <li>
      <Link
        href={withMerchPreviewParam(`/${locale}/supplies`, previewToken)}
        className={navLinkClassName}
      >
        {labels.supplies}
      </Link>
    </li>
  ) : null;

  return (
    <AppHeader
      variant="shop"
      data-testid="shop-header"
      appName={labels.appName}
      logo={
        <MerchPreviewLink
          href={`/${locale}`}
          className="inline-flex items-center transition-opacity duration-fast ease-std hover:opacity-90"
          aria-label={labels.appName}
        >
          <BrandLogo appName={labels.appName} />
        </MerchPreviewLink>
      }
      features={{ showLocale: false }}
      mobileSearchSlot={mobileSearchSlot}
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
      cartHref={withMerchPreviewParam(`/${locale}/cart`, previewToken)}
      cartLabel={labels.cart}
      cartCountLabel={cartCountLabel}
      cartSlot={
        <CartNavTrigger
          labels={{ openCart: cartCountLabel ?? labels.openCart }}
          cartIcon={
            <>
              <IconCart aria-hidden />
              <span className="sr-only lg:not-sr-only lg:ml-1.5">{labels.cart}</span>
            </>
          }
          className="relative inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing lg:min-w-0"
        />
      }
      accountLabel={labels.account}
      accountHref={withMerchPreviewParam(`/${locale}/account`, previewToken)}
      skipLinkTargetId="shop-main"
      skipLinkLabel={labels.skipToContent}
      navAriaLabel={labels.navAriaLabel}
      desktopNavAriaLabel={labels.desktopAriaLabel}
      LinkComponent={Link}
    />
  );
}
