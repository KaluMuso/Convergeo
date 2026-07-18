"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

type VendorQuickNavProps = {
  locale: string;
  /** Highlight the current primary destination when known. */
  active?: "home" | "listings" | "profile" | "orders";
};

/**
 * Compact mobile-first shortcuts — capability-based only (owner vendor app).
 * No staff/RBAC links (VEND-10 OUT of v1).
 */
export function VendorQuickNav({ locale, active }: VendorQuickNavProps) {
  const t = useTranslations("vendor");

  const items = [
    { key: "home" as const, href: `/${locale}`, label: t("shell.nav.home") },
    { key: "listings" as const, href: `/${locale}/listings`, label: t("shell.nav.listings") },
    { key: "orders" as const, href: `/${locale}/orders`, label: t("shell.nav.orders") },
    { key: "profile" as const, href: `/${locale}/profile`, label: t("shell.nav.profile") },
  ];

  return (
    <nav aria-label={t("shell.nav.ariaLabel")} className="border-b border-border bg-surface">
      <ul className="mx-auto flex max-w-lg gap-1 overflow-x-auto px-2 py-2">
        {items.map((item) => {
          const isActive = active === item.key;
          return (
            <li key={item.key} className="shrink-0">
              <Link
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={`inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium ${
                  isActive ? "bg-primary text-surface" : "text-text-2 hover:bg-bg-2 hover:text-text"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
