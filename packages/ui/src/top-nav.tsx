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
  skipLinkTargetId: string;
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
  skipLinkTargetId,
  navAriaLabel,
  LinkComponent = "a" as unknown as ComponentType<TopNavLinkProps>,
  className,
  condensed = false,
}: TopNavProps) {
  const [scrolled, setScrolled] = useState(false);

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
      id={skipLinkTargetId}
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
            aria-label={typeof cartLabel === "string" ? cartLabel : undefined}
          >
            <span aria-hidden>{cartIcon}</span>
            {cartCount > 0 ? (
              <span className="absolute -right-0.5 -top-0.5 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-semibold text-surface">
                {formatCartCount(cartCount)}
              </span>
            ) : null}
            {typeof cartLabel !== "string" ? <span className="sr-only">{cartLabel}</span> : null}
          </LinkComponent>
        </div>
      </nav>
    </header>
  );
}
