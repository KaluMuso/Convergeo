"use client";

import { IconAccount, IconCart } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getCartItemCount, useCartActions, useCartStore } from "./cart/mini-cart-drawer";
import { CategoryMegaMenu } from "./category-mega-menu";
import { DesktopHeaderSearch } from "./desktop-header-search";

import type { SearchInputLabels } from "./search/search-input";

type DesktopHeaderLabels = {
  appName: string;
  skipToContent: string;
  navAriaLabel: string;
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
  account: string;
  cart: string;
  cartWithCount: string;
  searchInput: SearchInputLabels;
};

type DesktopHeaderProps = {
  locale: string;
  labels: DesktopHeaderLabels;
  localeSwitcher?: React.ReactNode;
};

const SCROLL_COMPACT_PX = 48;

/**
 * Desktop-only (lg+) shop header — Logo · Search · Categories · Directory ·
 * Services · Events · Ask · Account · Cart. Theme lives in Preferences; Supplies
 * is demoted out of primary nav (account / gated routes). Sticky; mega-menu
 * closes on scroll.
 */
export function DesktopHeader({ locale, labels, localeSwitcher }: DesktopHeaderProps) {
  const [compact, setCompact] = useState(false);
  const { cart } = useCartStore();
  const { refresh } = useCartActions();

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let ticking = false;
    const update = () => {
      setCompact(window.scrollY > SCROLL_COMPACT_PX);
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

  const cartCount = getCartItemCount(cart);
  const cartAriaLabel =
    cartCount > 0
      ? labels.cartWithCount.replace("{count}", String(cartCount > 99 ? 99 : cartCount))
      : labels.cart;

  const navLinks = [
    { key: "directory", href: `/${locale}/directory`, label: labels.directory },
    { key: "services", href: `/${locale}/services`, label: labels.services },
    { key: "events", href: `/${locale}/events`, label: labels.events },
    { key: "ask", href: `/${locale}/ask`, label: labels.askVergeo },
  ];

  return (
    <header
      data-testid="desktop-header"
      data-compact={compact ? "true" : "false"}
      className="sticky top-0 z-50 hidden border-b border-border bg-surface lg:block"
      style={{
        boxShadow: compact ? "var(--shadow-1)" : "none",
        transition: "box-shadow var(--dur) var(--ease-std)",
      }}
    >
      <a
        href="#shop-main"
        className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
      >
        {labels.skipToContent}
      </a>
      <nav
        aria-label={labels.navAriaLabel}
        className="mx-auto flex w-full max-w-7xl items-center gap-4 px-6 transition-[height] duration-fast ease-std motion-reduce:transition-none"
        style={{ height: compact ? "3.5rem" : "4rem" }}
      >
        <Link
          href={`/${locale}`}
          className="shrink-0 font-display text-2xl leading-none text-primary transition-transform duration-fast ease-std"
        >
          {labels.appName}
        </Link>

        <div className="min-w-0 max-w-3xl flex-1 xl:max-w-4xl">
          <DesktopHeaderSearch locale={locale} labels={labels.searchInput} />
        </div>

        <ul className="flex shrink-0 list-none items-center gap-0.5 p-0">
          <li>
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
          </li>
          {navLinks.map((link) => (
            <li key={link.key}>
              <Link
                href={link.href}
                className="inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          {localeSwitcher}
          <Link
            href={`/${locale}/account`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            <IconAccount />
            <span className={compact ? "sr-only" : undefined}>{labels.account}</span>
          </Link>
          <Link
            href={`/${locale}/cart`}
            aria-label={cartAriaLabel}
            className="relative inline-flex min-h-11 items-center gap-1.5 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            <IconCart aria-hidden />
            {cartCount > 0 ? (
              <span
                aria-hidden
                className="absolute right-1 top-1 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-semibold text-surface"
              >
                {cartCount > 99 ? "99+" : cartCount}
              </span>
            ) : null}
            <span className={compact ? "sr-only" : undefined}>{labels.cart}</span>
          </Link>
          <span className="sr-only" aria-live="polite" aria-atomic="true">
            {cartCount > 0 ? cartAriaLabel : ""}
          </span>
        </div>
      </nav>
    </header>
  );
}
