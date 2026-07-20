"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { SignOutButton } from "./sign-out-button";

export type AccountNavLabels = {
  ariaLabel: string;
  overview: string;
  orders: string;
  tickets: string;
  jobs: string;
  saved: string;
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
};

type NavItem = {
  key: keyof Omit<AccountNavLabels, "ariaLabel" | "signOut" | "signingOut">;
  href: (locale: string) => string;
};

const NAV_ITEMS: NavItem[] = [
  { key: "overview", href: (locale) => `/${locale}/account` },
  { key: "orders", href: (locale) => `/${locale}/account/orders` },
  { key: "tickets", href: (locale) => `/${locale}/account/tickets` },
  { key: "jobs", href: (locale) => `/${locale}/account/jobs` },
  { key: "saved", href: (locale) => `/${locale}/wishlist` },
  { key: "addresses", href: (locale) => `/${locale}/account/addresses` },
  { key: "preferences", href: (locale) => `/${locale}/account/preferences` },
  { key: "profile", href: (locale) => `/${locale}/account/profile` },
  { key: "business", href: (locale) => `/${locale}/account/business` },
  { key: "privacy", href: (locale) => `/${locale}/account/privacy` },
];

export function AccountNav({ locale, labels }: AccountNavProps) {
  const pathname = usePathname();

  return (
    <nav
      aria-label={labels.ariaLabel}
      className="mb-6 flex gap-2 overflow-x-auto pb-1"
      data-testid="account-nav"
    >
      {NAV_ITEMS.map((item) => {
        const href = item.href(locale);
        const isActive =
          item.key === "overview"
            ? pathname === href || pathname === `${href}/`
            : pathname === href || pathname.startsWith(`${href}/`);

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
    </nav>
  );
}
