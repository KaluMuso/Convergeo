"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";

import { IconAccount, IconCart } from "./icons";

export type AppHeaderVariant = "shop" | "auth" | "account" | "marketing";

export type AppHeaderBrandProminence = "compact" | "hero";

export type AppHeaderFeatures = {
  showSearch?: boolean;
  showCategories?: boolean;
  showCart?: boolean;
  showAccount?: boolean;
  showLocale?: boolean;
  showSignIn?: boolean;
  brandProminence?: AppHeaderBrandProminence;
};

export type AppHeaderLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
};

export type AppHeaderNavLink = {
  key: string;
  href: string;
  label: string;
};

export type AppHeaderProps = {
  variant: AppHeaderVariant;
  features?: AppHeaderFeatures;
  appName: string;
  tagline?: string;
  logoHref?: string;
  logo?: ReactNode;
  /** Mobile search affordance (link or compact input). */
  mobileSearchSlot?: ReactNode;
  /** Desktop search input (typically wider). */
  desktopSearchSlot?: ReactNode;
  /** Category mega-menu trigger + panel (desktop). */
  categoriesSlot?: ReactNode;
  /** Primary nav links (Directory, Services, …) — desktop row. */
  navLinks?: AppHeaderNavLink[];
  /** Gated Supplies link — rendered inside the desktop nav list when provided. */
  suppliesSlot?: ReactNode;
  localeSwitcher?: ReactNode;
  /** Auth variant: “Back to shop” / Help link. */
  secondaryLink?: ReactNode;
  signInSlot?: ReactNode;
  cartCount?: number;
  cartHref?: string;
  cartLabel?: string;
  cartCountLabel?: string;
  accountLabel?: string;
  accountHref?: string;
  /** When set, replaces the default account link (e.g. account menu dropdown). */
  accountMenuSlot?: ReactNode;
  skipLinkTargetId: string;
  skipLinkLabel?: string;
  navAriaLabel: string;
  desktopNavAriaLabel?: string;
  LinkComponent?: ComponentType<AppHeaderLinkProps>;
  className?: string;
  "data-testid"?: string;
};

const VARIANT_DEFAULTS: Record<AppHeaderVariant, Required<AppHeaderFeatures>> = {
  shop: {
    showSearch: true,
    showCategories: true,
    showCart: true,
    showAccount: true,
    showLocale: true,
    showSignIn: false,
    brandProminence: "compact",
  },
  auth: {
    showSearch: false,
    showCategories: false,
    showCart: false,
    showAccount: false,
    showLocale: true,
    showSignIn: false,
    brandProminence: "hero",
  },
  account: {
    showSearch: true,
    showCategories: false,
    showCart: true,
    showAccount: true,
    showLocale: true,
    showSignIn: false,
    brandProminence: "compact",
  },
  marketing: {
    showSearch: true,
    showCategories: false,
    showCart: false,
    showAccount: false,
    showLocale: true,
    showSignIn: true,
    brandProminence: "compact",
  },
};

const SCROLL_COMPACT_PX = 48;

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function formatCartCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

function resolveFeatures(
  variant: AppHeaderVariant,
  overrides?: AppHeaderFeatures,
): Required<AppHeaderFeatures> {
  return { ...VARIANT_DEFAULTS[variant], ...overrides };
}

const navLinkClassName =
  "inline-flex min-h-11 items-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing";

export function AppHeader({
  variant,
  features: featureOverrides,
  appName,
  tagline,
  logoHref = "/",
  logo,
  mobileSearchSlot,
  desktopSearchSlot,
  categoriesSlot,
  navLinks = [],
  suppliesSlot,
  localeSwitcher,
  secondaryLink,
  signInSlot,
  cartCount = 0,
  cartHref = "#",
  cartLabel = "",
  cartCountLabel,
  accountLabel,
  accountHref = "#",
  accountMenuSlot,
  skipLinkTargetId,
  skipLinkLabel,
  navAriaLabel,
  desktopNavAriaLabel,
  LinkComponent = "a" as unknown as ComponentType<AppHeaderLinkProps>,
  className,
  "data-testid": dataTestId,
}: AppHeaderProps) {
  const features = resolveFeatures(variant, featureOverrides);
  const [compact, setCompact] = useState(false);
  const isHero = features.brandProminence === "hero";

  const cartAccessibleName = (() => {
    if (cartCount <= 0) {
      return cartLabel;
    }
    if (cartCountLabel) {
      return cartCountLabel;
    }
    return `${cartLabel}, ${formatCartCount(cartCount)}`;
  })();
  const cartStatusText =
    cartCount > 0 ? (cartCountLabel ?? `${cartLabel}: ${formatCartCount(cartCount)}`) : "";

  useEffect(() => {
    if (isHero) {
      return;
    }

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
  }, [isHero]);

  const skipLink = skipLinkLabel ? (
    <a
      href={`#${skipLinkTargetId}`}
      className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
    >
      {skipLinkLabel}
    </a>
  ) : null;

  const wordmark = logo ?? (
    <LinkComponent href={logoHref} className="font-display text-primary">
      {appName}
    </LinkComponent>
  );

  const cartButton = features.showCart ? (
    <LinkComponent
      href={cartHref}
      className="relative inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing lg:min-w-0"
      aria-label={cartAccessibleName}
    >
      <IconCart aria-hidden />
      {cartCount > 0 ? (
        <span
          aria-hidden
          className="absolute right-1 top-1 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-semibold text-surface lg:right-0.5 lg:top-0.5"
        >
          {formatCartCount(cartCount)}
        </span>
      ) : null}
      <span className={compact ? "sr-only lg:not-sr-only" : undefined}>{cartLabel}</span>
    </LinkComponent>
  ) : null;

  const cartLiveRegion =
    features.showCart && cartStatusText ? (
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {cartStatusText}
      </span>
    ) : null;

  const accountControl = accountMenuSlot ? (
    accountMenuSlot
  ) : features.showAccount && accountLabel ? (
    <LinkComponent href={accountHref} className={navLinkClassName}>
      <IconAccount aria-hidden />
      <span className={compact ? "sr-only lg:not-sr-only" : undefined}>{accountLabel}</span>
    </LinkComponent>
  ) : null;

  const localeControl = features.showLocale ? localeSwitcher : null;
  const signInControl = features.showSignIn ? signInSlot : null;

  if (isHero) {
    return (
      <header
        data-testid={dataTestId ?? "app-header"}
        data-variant={variant}
        className={mergeClasses(
          "relative left-1/2 right-1/2 -ml-[50vw] -mr-[50vw] w-screen overflow-hidden bg-panel text-panel-text",
          className,
        )}
      >
        {skipLink}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-90"
          style={{
            background:
              "radial-gradient(120% 80% at 85% 20%, color-mix(in srgb, var(--primary) 35%, transparent) 0%, transparent 55%), linear-gradient(135deg, var(--panel) 0%, color-mix(in srgb, var(--primary-deep) 55%, var(--panel)) 100%)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-6 top-4 h-36 w-36 rounded-full bg-primary/20 blur-2xl motion-reduce:blur-none sm:h-48 sm:w-48"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute bottom-0 left-[10%] h-28 w-28 rounded-full bg-accent/15 blur-xl motion-reduce:blur-none"
        />

        <div className="relative mx-auto flex w-full max-w-lg flex-col gap-4 px-4 pb-2 pt-3 sm:max-w-2xl">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">{secondaryLink}</div>
            <div className="flex shrink-0 items-center gap-2">
              {signInControl}
              {localeControl}
            </div>
          </div>

          <div className="flex flex-col items-center gap-2 pb-6 pt-2 text-center sm:pb-8 sm:pt-4">
            <p
              data-testid="app-header-wordmark"
              className="font-display text-hero leading-none tracking-tight text-panel-text"
            >
              {appName}
            </p>
            {tagline ? (
              <p className="max-w-xs font-body text-body text-panel-muted">{tagline}</p>
            ) : null}
          </div>
        </div>
      </header>
    );
  }

  return (
    <header
      data-testid={dataTestId ?? "app-header"}
      data-variant={variant}
      data-compact={compact ? "true" : "false"}
      className={mergeClasses("sticky top-0 z-50 border-b border-border bg-surface", className)}
      style={{
        boxShadow: compact ? "var(--shadow-1)" : "none",
        transition: "box-shadow var(--dur) var(--ease-std)",
      }}
    >
      {skipLink}
      {cartLiveRegion}

      {/* Mobile / tablet (< lg) */}
      <nav
        aria-label={navAriaLabel}
        className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-3 lg:hidden"
      >
        <div className="flex w-full items-center justify-between gap-3">
          <div className="min-w-0 shrink-0 [&_a]:text-lg [&_a]:leading-none">{wordmark}</div>
          <div className="flex shrink-0 items-center gap-1">
            {localeControl}
            {signInControl}
            {accountControl}
            {cartButton}
          </div>
        </div>
        {features.showSearch && mobileSearchSlot ? (
          <div className="w-full min-w-0">{mobileSearchSlot}</div>
        ) : null}
      </nav>

      {/* Desktop (lg+) */}
      <nav
        aria-label={desktopNavAriaLabel ?? navAriaLabel}
        className="mx-auto hidden w-full max-w-7xl items-center gap-4 px-6 transition-[height] duration-fast ease-std motion-reduce:transition-none lg:flex"
        style={{ height: compact ? "3.5rem" : "4rem" }}
      >
        <div className="shrink-0 [&_a]:text-2xl [&_a]:leading-none [&_a]:transition-transform [&_a]:duration-fast [&_a]:ease-std">
          {wordmark}
        </div>

        {features.showSearch && desktopSearchSlot ? (
          <div className="min-w-0 max-w-3xl flex-1 xl:max-w-4xl">{desktopSearchSlot}</div>
        ) : null}

        {(features.showCategories && categoriesSlot) || navLinks.length > 0 || suppliesSlot ? (
          <ul className="flex shrink-0 list-none items-center gap-0.5 p-0">
            {features.showCategories && categoriesSlot ? <li>{categoriesSlot}</li> : null}
            {navLinks.map((link) => (
              <li key={link.key}>
                <LinkComponent href={link.href} className={navLinkClassName}>
                  {link.label}
                </LinkComponent>
              </li>
            ))}
            {suppliesSlot}
          </ul>
        ) : null}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          {localeControl}
          {signInControl}
          {accountControl}
          {cartButton}
        </div>
      </nav>
    </header>
  );
}
