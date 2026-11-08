"use client";

import { IconAccount, IconCart } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { BrandLogo } from "./brand-logo";
import { CartNavTrigger, getCartItemCount, setStoreState, useCartStore } from "./cart/cart-store";
import { CategoryMegaMenu } from "./category-mega-menu";
import { DesktopHeaderSearch } from "./desktop-header-search";
import { HeaderThemeToggle } from "./header-theme-toggle";
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
  /** Appearance quick toggle (common.theme.*). */
  theme?: { label: string; light: string; dark: string; system: string };
};

type ShopHeaderProps = {
  locale: string;
  labels: ShopHeaderLabels;
  /** @deprecated Locale lives in the utility bar; kept for call-site compatibility. */
  localeSwitcher?: React.ReactNode;
  /** Mobile search affordance — typically `MobileHeaderSearch` from the layout. */
  mobileSearchSlot?: ReactNode;
};

/** Pill chip on tablet's scroller row, plain nav link on desktop. */
const navLinkClassName =
  "inline-flex min-h-11 items-center rounded-pill border border-border px-3.5 text-sm font-medium text-text-2 transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing lg:rounded lg:border-transparent lg:px-3 lg:hover:border-transparent lg:hover:bg-bg-2 lg:hover:text-text";

const actionClassName =
  "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded px-3 text-sm font-semibold text-text transition-colors hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing";

/**
 * Storefront header (owner pass 2): full-bleed glass bar that blends into the
 * page below. Phones: logo + actions, search row (bottom nav carries the rest).
 * Tablet: one bar + category/vertical scroller. Desktop: logo · All categories
 * · search (with Ask Vergeo sparkle) · Directory · Services · Events · Account
 * · Cart. Cart/account show icon + label side by side, count on the icon.
 */
export function ShopHeader({ locale, labels, mobileSearchSlot }: ShopHeaderProps) {
  const previewToken = useMerchPreviewToken();
  const { cart } = useCartStore();
  const eligibleForSupplies = useBusinessEligibility();

  useEffect(() => {
    // Defer cart hydration until after first paint so header mount does not
    // contend with LCP on home/checkout under Fast-3G CI budgets.
    let cancelled = false;
    const run = () => {
      if (!cancelled) {
        void import("./cart/mini-cart-drawer")
          .then(({ refreshCart }) => {
            if (!cancelled) void refreshCart();
          })
          .catch(() => {
            if (!cancelled) setStoreState({ loading: false, loadError: true });
          });
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
  }, []);

  const cartCount = getCartItemCount(cart);
  const cartCountLabel =
    cartCount > 0
      ? labels.cartWithCount.replace("{count}", String(cartCount > 99 ? 99 : cartCount))
      : undefined;

  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    let ticking = false;
    const update = () => {
      setScrolled(window.scrollY > 8);
      ticking = false;
    };
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Order agreed with the owner: Directory · Services · Events (Ask Vergeo
  // moved into the search field as the sparkle button).
  const navLinks = [
    { key: "directory", href: `/${locale}/directory`, label: labels.directory },
    { key: "services", href: `/${locale}/services`, label: labels.services },
    { key: "events", href: `/${locale}/events`, label: labels.events },
  ].map((link) => ({
    ...link,
    href: withMerchPreviewParam(link.href, previewToken),
  }));
  const suppliesHref = withMerchPreviewParam(`/${locale}/supplies`, previewToken);
  const accountHref = withMerchPreviewParam(`/${locale}/account`, previewToken);

  const logo = (
    <MerchPreviewLink
      href={`/${locale}`}
      className="inline-flex shrink-0 items-center rounded-sm transition-opacity duration-fast ease-std hover:opacity-90 focus-visible:outline-none focus-visible:shadow-focusRing"
      aria-label={labels.appName}
    >
      <BrandLogo appName={labels.appName} />
    </MerchPreviewLink>
  );

  const categories = (
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
  );

  const accountLink = (withLabel: boolean) => (
    <Link
      href={accountHref}
      className={`${actionClassName} ${withLabel ? "" : "px-2"}`}
      aria-label={withLabel ? undefined : labels.account}
    >
      <IconAccount aria-hidden />
      {withLabel ? <span>{labels.account}</span> : null}
    </Link>
  );

  const cartTrigger = (withLabel: boolean) => (
    <CartNavTrigger
      labels={{ openCart: cartCountLabel ?? labels.openCart }}
      cartIcon={<IconCart aria-hidden />}
      label={withLabel ? labels.cart : undefined}
      className={`relative ${actionClassName} ${withLabel ? "" : "px-2"}`}
    />
  );

  const themeToggle = labels.theme ? <HeaderThemeToggle labels={labels.theme} /> : null;

  return (
    <header
      data-testid="shop-header"
      data-scrolled={scrolled ? "true" : "false"}
      className="v-shop-header sticky top-0 z-50 w-full"
    >
      <a
        href="#shop-main"
        className="sr-only rounded bg-primary text-sm font-medium text-[var(--primary-btn-fg)] focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4"
      >
        {labels.skipToContent}
      </a>

      {/* Phones (< md): logo + actions, then a full-width search row. */}
      <nav aria-label={labels.navAriaLabel} className="flex flex-col gap-2 px-4 pb-3 pt-2 md:hidden">
        <div className="flex items-center justify-between gap-2">
          {logo}
          <div className="flex items-center gap-0.5">
            {themeToggle}
            {accountLink(false)}
            {cartTrigger(false)}
          </div>
        </div>
        {mobileSearchSlot ? <div className="w-full min-w-0">{mobileSearchSlot}</div> : null}
      </nav>

      {/* Tablet + desktop (md+), full-bleed. Desktop is one row:
          logo · All categories · search · Directory/Services/Events · Account · Cart.
          Tablet wraps categories + verticals into a scroller row under the bar
          (same elements re-ordered with CSS, so nothing renders twice). */}
      <nav
        aria-label={labels.desktopAriaLabel}
        className="hidden flex-wrap items-center gap-x-2 px-4 md:flex lg:h-16 lg:flex-nowrap lg:gap-x-3 lg:px-6 xl:px-8"
      >
        <div className="order-1 flex h-16 items-center">{logo}</div>
        <div className="order-2 mx-1 min-w-0 flex-1 lg:order-3 lg:mx-2 lg:max-w-xl xl:max-w-2xl">
          <DesktopHeaderSearch
            locale={locale}
            labels={labels.searchInput}
            askLabel={labels.askVergeo}
          />
        </div>
        <div className="order-3 ml-auto flex shrink-0 items-center gap-0.5 lg:order-5 lg:ml-0">
          {themeToggle}
          {accountLink(true)}
          {cartTrigger(true)}
        </div>
        <div className="order-4 flex basis-full items-center gap-1 overflow-x-auto pb-2 [scrollbar-width:none] lg:contents">
          <div className="shrink-0 lg:order-2">{categories}</div>
          <ul className="m-0 flex list-none items-center gap-1 p-0 lg:order-4 lg:gap-0.5">
            {navLinks.map((link) => (
              <li key={link.key} className="shrink-0">
                <Link href={link.href} className={navLinkClassName}>
                  {link.label}
                </Link>
              </li>
            ))}
            {eligibleForSupplies ? (
              <li className="shrink-0">
                <Link href={suppliesHref} className={navLinkClassName}>
                  {labels.supplies}
                </Link>
              </li>
            ) : null}
          </ul>
        </div>
      </nav>
    </header>
  );
}
