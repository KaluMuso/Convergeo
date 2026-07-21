"use client";

import { IconAccount } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { SignOutButton } from "./sign-out-button";

import type { AccountHeaderClientLabels } from "./account-header-client";

type AccountHeaderMenuProps = {
  locale: string;
  labels: Pick<
    AccountHeaderClientLabels,
    | "accountMenuAria"
    | "accountOverview"
    | "accountOrders"
    | "accountPreferences"
    | "signOut"
    | "signingOut"
  >;
};

export function AccountHeaderMenu({ locale, labels }: AccountHeaderMenuProps) {
  const detailsRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const details = detailsRef.current;
    if (!details) {
      return;
    }

    const closeOnOutside = (event: MouseEvent) => {
      if (!details.open) {
        return;
      }
      if (event.target instanceof Node && !details.contains(event.target)) {
        details.open = false;
      }
    };

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && details.open) {
        details.open = false;
      }
    };

    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const menuItems = [
    { key: "overview", href: `/${locale}/account`, label: labels.accountOverview },
    { key: "orders", href: `/${locale}/account/orders`, label: labels.accountOrders },
    {
      key: "preferences",
      href: `/${locale}/account/preferences`,
      label: labels.accountPreferences,
    },
  ];

  return (
    <details ref={detailsRef} className="relative">
      <summary
        className="inline-flex min-h-11 min-w-11 cursor-pointer list-none items-center justify-center rounded text-primary marker:content-none focus-visible:outline-none focus-visible:shadow-focusRing [&::-webkit-details-marker]:hidden"
        aria-label={labels.accountMenuAria}
      >
        <IconAccount aria-hidden />
      </summary>
      <div
        role="menu"
        className="absolute right-0 top-full z-50 mt-1 min-w-44 rounded-lg border border-border bg-surface py-1 shadow-2"
      >
        {menuItems.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            role="menuitem"
            className="block px-4 py-2 text-sm text-text hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
            onClick={() => {
              if (detailsRef.current) {
                detailsRef.current.open = false;
              }
            }}
          >
            {item.label}
          </Link>
        ))}
        <div className="border-t border-border px-4 py-2">
          <SignOutButton locale={locale} label={labels.signOut} loadingLabel={labels.signingOut} />
        </div>
      </div>
    </details>
  );
}
