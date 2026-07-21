"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";

export type AppHeaderVariant = "account" | "marketing" | "shop";

export type AppHeaderLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  "aria-current"?: "page" | boolean;
};

export type AppHeaderNavLink = {
  key: string;
  href: string;
  label: string;
};

export type AppHeaderProps = {
  variant: AppHeaderVariant;
  logo: ReactNode;
  navAriaLabel: string;
  /** Primary text links (marketing variant). */
  links?: AppHeaderNavLink[];
  /** Search control (account / shop variants). */
  searchSlot?: ReactNode;
  /** Prominent sign-in CTA (marketing variant). */
  signInSlot?: ReactNode;
  /** Trailing utilities (locale switcher, etc.). */
  trailingSlot?: ReactNode;
  /** Cart control with badge (account / shop variants). */
  cartSlot?: ReactNode;
  /** Account menu trigger + panel (account variant). */
  accountMenuSlot?: ReactNode;
  /** Optional skip link — omit when the parent layout owns the landmark jump. */
  skipLink?: { targetId: string; label: string };
  LinkComponent?: ComponentType<AppHeaderLinkProps>;
  className?: string;
};

const SCROLL_SHADOW_THRESHOLD_PX = 40;

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Unified application header primitive (A1).
 *
 * Variants:
 * - `marketing` — logo, primary marketing links, prominent sign-in CTA
 * - `account` — logo, search, cart, account menu
 * - `shop` — reserved for shop layout adoption (A1 shop pebble)
 */
export function AppHeader({
  variant,
  logo,
  navAriaLabel,
  links = [],
  searchSlot,
  signInSlot,
  trailingSlot,
  cartSlot,
  accountMenuSlot,
  skipLink,
  LinkComponent = "a" as unknown as ComponentType<AppHeaderLinkProps>,
  className,
}: AppHeaderProps) {
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

  const isMarketing = variant === "marketing";
  const isAccount = variant === "account";

  return (
    <header
      data-testid="app-header"
      data-variant={variant}
      className={mergeClasses(
        "sticky top-0 z-50 border-b border-border bg-bg",
        scrolled && "app-header--scrolled",
        className,
      )}
      style={{
        boxShadow: scrolled ? "var(--shadow-1)" : "none",
        transition: "box-shadow var(--dur) var(--ease-std)",
      }}
    >
      {skipLink ? (
        <a
          href={`#${skipLink.targetId}`}
          className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
        >
          {skipLink.label}
        </a>
      ) : null}

      <nav
        aria-label={navAriaLabel}
        className={mergeClasses(
          "mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3",
          isMarketing ? "flex-wrap lg:flex-nowrap lg:gap-4 lg:px-6" : "gap-2 lg:px-6",
        )}
      >
        <div className="flex shrink-0 items-center">{logo}</div>

        {isMarketing ? (
          <>
            <ul className="m-0 hidden min-w-0 flex-1 list-none items-center gap-0.5 p-0 lg:flex">
              {links.map((link) => (
                <li key={link.key}>
                  <LinkComponent
                    href={link.href}
                    className="inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
                  >
                    {link.label}
                  </LinkComponent>
                </li>
              ))}
            </ul>
            <div className="ml-auto flex shrink-0 items-center gap-2">
              {trailingSlot}
              {signInSlot}
            </div>
          </>
        ) : null}

        {isAccount ? (
          <>
            {searchSlot ? <div className="min-w-0 flex-1">{searchSlot}</div> : null}
            <div className="flex shrink-0 items-center gap-1">
              {trailingSlot}
              {accountMenuSlot}
              {cartSlot}
            </div>
          </>
        ) : null}
      </nav>

      {isMarketing && links.length > 0 ? (
        <div className="border-t border-border bg-surface px-4 py-2 lg:hidden">
          <ul className="m-0 flex list-none gap-1 overflow-x-auto p-0">
            {links.map((link) => (
              <li key={link.key} className="shrink-0">
                <LinkComponent
                  href={link.href}
                  className="inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {link.label}
                </LinkComponent>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </header>
  );
}
