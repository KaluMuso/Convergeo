"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";

export type TopNavLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
};

export type TopNavProps = {
  logo: ReactNode;
  searchSlot?: ReactNode;
  actions?: ReactNode;
  cartIcon: ReactNode;
  cartCount?: number;
  cartHref?: string;
  cartLabel: ReactNode;
  /**
   * Accessible name when the cart has items. Prefer a localised ICU string
   * (`Cart, {count} items`). Falls back to `${cartLabel}, {count}` when omitted.
   */
  cartCountLabel?: string;
  /** Id of the main-content landmark this nav's skip link jumps to. */
  skipLinkTargetId: string;
  /** Localised "Skip to content" label. When provided, a keyboard-visible skip link renders first. */
  skipLinkLabel?: string;
  navAriaLabel: string;
  LinkComponent?: ComponentType<TopNavLinkProps>;
  className?: string;
  /** When true, main row stacks vertically (condensed layout). */
  condensed?: boolean;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function formatCartCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

const SCROLL_SHADOW_THRESHOLD_PX = 40;

export function TopNav({
  logo,
  searchSlot,
  actions,
  cartIcon,
  cartCount = 0,
  cartHref = "#",
  cartLabel,
  cartCountLabel,
  skipLinkTargetId,
  skipLinkLabel,
  navAriaLabel,
  LinkComponent = "a" as unknown as ComponentType<TopNavLinkProps>,
  className,
  condensed = false,
}: TopNavProps) {
  const [scrolled, setScrolled] = useState(false);
  const cartAccessibleName = (() => {
    if (typeof cartLabel !== "string") {
      return undefined;
    }
    if (cartCount <= 0) {
      return cartLabel;
    }
    if (cartCountLabel) {
      return cartCountLabel;
    }
    return `${cartLabel}, ${formatCartCount(cartCount)}`;
  })();
  const cartStatusText =
    cartCount > 0 && typeof cartLabel === "string"
      ? (cartCountLabel ?? `${cartLabel}: ${formatCartCount(cartCount)}`)
      : "";

  useEffect(() => {
    let ticking = false;

    const updateScrolled = () => {
      setScrolled(window.scrollY > SCROLL_SHADOW_THRESHOLD_PX);
      ticking = false;
    };

    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(updateScrolled);
      }
    };

    updateScrolled();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={mergeClasses(
        "sticky top-0 z-50 border-b border-border bg-bg",
        scrolled && "top-nav--scrolled",
        className,
      )}
      style={{
        boxShadow: scrolled ? "var(--shadow-1)" : "none",
        transition: "box-shadow var(--dur) var(--ease-std)",
      }}
    >
      {skipLinkLabel ? (
        <a
          href={`#${skipLinkTargetId}`}
          className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
        >
          {skipLinkLabel}
        </a>
      ) : null}
      <nav
        aria-label={navAriaLabel}
        className={mergeClasses(
          "mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3",
          condensed ? "flex-col" : "flex-row",
        )}
      >
        <div
          className={mergeClasses(
            "flex shrink-0 items-center",
            condensed && "w-full justify-between",
          )}
        >
          {logo}
        </div>
        {searchSlot ? (
          <div className={mergeClasses("min-w-0 flex-1", condensed && "w-full")}>{searchSlot}</div>
        ) : null}
        <div
          className={mergeClasses(
            "flex shrink-0 items-center gap-2",
            condensed && "w-full justify-end",
          )}
        >
          {actions}
          <LinkComponent
            href={cartHref}
            className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded text-primary"
            aria-label={cartAccessibleName}
          >
            <span aria-hidden>{cartIcon}</span>
            {cartCount > 0 ? (
              <span
                aria-hidden
                className="absolute -right-0.5 -top-0.5 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-semibold text-surface"
              >
                {formatCartCount(cartCount)}
              </span>
            ) : null}
            {typeof cartLabel !== "string" ? <span className="sr-only">{cartLabel}</span> : null}
          </LinkComponent>
          <span className="sr-only" aria-live="polite" aria-atomic="true">
            {cartStatusText}
          </span>
        </div>
      </nav>
    </header>
  );
}
