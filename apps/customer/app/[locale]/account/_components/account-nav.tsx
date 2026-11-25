"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { SignOutButton } from "./sign-out-button";

export type AccountNavLabels = {
  ariaLabel: string;
  overview: string;
  orders: string;
  rewards: string;
  tickets: string;
  jobs: string;
  quotes: string;
  saved: string;
  following: string;
  people?: string;
  addresses: string;
  preferences: string;
  profile: string;
  privacy: string;
  business: string;
  signOut: string;
  signingOut: string;
};

type AccountNavProps = {
  locale: string;
  labels: AccountNavLabels;
  showPeople?: boolean;
};

type NavItem = {
  key: keyof Omit<AccountNavLabels, "ariaLabel" | "signOut" | "signingOut">;
  href: (locale: string) => string;
};

const NAV_ITEMS: NavItem[] = [
  { key: "overview", href: (locale) => `/${locale}/account` },
  { key: "orders", href: (locale) => `/${locale}/account/orders` },
  { key: "rewards", href: (locale) => `/${locale}/account/rewards` },
  { key: "tickets", href: (locale) => `/${locale}/account/tickets` },
  { key: "jobs", href: (locale) => `/${locale}/account/jobs` },
  { key: "quotes", href: (locale) => `/${locale}/account/quotes` },
  { key: "saved", href: (locale) => `/${locale}/wishlist` },
  { key: "following", href: (locale) => `/${locale}/account/following` },
  { key: "people", href: (locale) => `/${locale}/account/people/contacts` },
  { key: "addresses", href: (locale) => `/${locale}/account/addresses` },
  { key: "preferences", href: (locale) => `/${locale}/account/preferences` },
  { key: "profile", href: (locale) => `/${locale}/account/profile` },
  { key: "business", href: (locale) => `/${locale}/account/business` },
  { key: "privacy", href: (locale) => `/${locale}/account/privacy` },
];

type ScrollFade = { left: boolean; right: boolean };

function isActivePath(pathname: string, href: string, key: NavItem["key"]): boolean {
  if (key === "overview") {
    return pathname === href || pathname === `${href}/`;
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AccountNav({ locale, labels, showPeople = false }: AccountNavProps) {
  const pathname = usePathname() ?? `/${locale}/account`;
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [scrollFade, setScrollFade] = useState<ScrollFade>({
    left: false,
    right: false,
  });

  const updateScrollFade = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) {
      return;
    }
    const isWide =
      typeof window.matchMedia === "function" && window.matchMedia("(min-width: 1024px)").matches;
    if (isWide) {
      setScrollFade({ left: false, right: false });
      return;
    }
    const { scrollLeft, scrollWidth, clientWidth } = el;
    setScrollFade({
      left: scrollLeft > 2,
      right: scrollLeft + clientWidth < scrollWidth - 2,
    });
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) {
      return;
    }
    const active = el.querySelector<HTMLElement>('[aria-current="page"]');
    if (active && typeof active.scrollIntoView === "function") {
      active.scrollIntoView({
        inline: "center",
        block: "nearest",
        behavior: "auto",
      });
    }
    updateScrollFade();
    el.addEventListener("scroll", updateScrollFade, { passive: true });
    const onResize = () => updateScrollFade();
    window.addEventListener("resize", onResize);
    const observer =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => updateScrollFade()) : null;
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", updateScrollFade);
      window.removeEventListener("resize", onResize);
      observer?.disconnect();
    };
  }, [pathname, updateScrollFade]);

  return (
    <nav aria-label={labels.ariaLabel} className="mb-6" data-testid="account-nav">
      <div className="relative max-lg:-mx-4 max-lg:px-4">
        {scrollFade.left ? (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-0 z-[1] w-8 bg-gradient-to-r from-bg via-bg/80 to-transparent max-lg:block lg:hidden"
            data-testid="account-nav-fade-left"
          />
        ) : null}
        {scrollFade.right ? (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 z-[1] w-8 bg-gradient-to-l from-bg via-bg/80 to-transparent max-lg:block lg:hidden"
            data-testid="account-nav-fade-right"
          />
        ) : null}
        <div
          ref={scrollerRef}
          data-testid="account-nav-rail"
          className="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden max-lg:flex-nowrap lg:flex-wrap lg:overflow-x-visible"
        >
          {NAV_ITEMS.map((item) => {
            if (item.key === "people" && (!showPeople || !labels.people)) {
              return null;
            }
            const href = item.href(locale);
            const isActive = isActivePath(pathname, href, item.key);

            return (
              <Link
                key={item.key}
                href={href}
                aria-current={isActive ? "page" : undefined}
                className={[
                  "inline-flex min-h-11 shrink-0 items-center rounded px-4 text-sm font-medium",
                  "transition-colors duration-fast ease-std motion-reduce:transition-none",
                  isActive
                    ? "bg-primary text-surface"
                    : "border border-border bg-surface text-text hover:bg-bg-2",
                ].join(" ")}
              >
                {labels[item.key]}
              </Link>
            );
          })}
          <SignOutButton locale={locale} label={labels.signOut} loadingLabel={labels.signingOut} />
        </div>
      </div>
    </nav>
  );
}
