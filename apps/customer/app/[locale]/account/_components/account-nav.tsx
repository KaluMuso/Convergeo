"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export type AccountNavLabels = {
  ariaLabel: string;
  profile: string;
  addresses: string;
  preferences: string;
  privacy: string;
};

type AccountNavProps = {
  locale: string;
  labels: AccountNavLabels;
};

const NAV_ITEMS = [
  { key: "profile", segment: "" },
  { key: "addresses", segment: "addresses" },
  { key: "preferences", segment: "preferences" },
  { key: "privacy", segment: "privacy" },
] as const;

export function AccountNav({ locale, labels }: AccountNavProps) {
  const pathname = usePathname();

  return (
    <nav aria-label={labels.ariaLabel} className="mb-6 flex gap-2 overflow-x-auto pb-1">
      {NAV_ITEMS.map((item) => {
        const href = `/${locale}/account${item.segment ? `/${item.segment}` : ""}`;
        const isActive =
          item.segment === ""
            ? pathname === href || pathname === `${href}/`
            : pathname.startsWith(href);

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
    </nav>
  );
}
