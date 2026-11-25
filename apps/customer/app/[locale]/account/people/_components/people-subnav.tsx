"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

type PeopleSubnavProps = { locale: string; requestBadge?: number };

const LINKS = [
  { key: "contacts", suffix: "contacts" },
  { key: "requests", suffix: "requests" },
  { key: "add", suffix: "add" },
] as const;

export function PeopleSubnav({ locale, requestBadge = 0 }: PeopleSubnavProps) {
  const pathname = usePathname() ?? "";
  const t = useTranslations("social.nav");

  return (
    <nav className="mb-6 flex flex-wrap gap-2" aria-label={t("contacts")}>
      {LINKS.map((link) => {
        const href = `/${locale}/account/people/${link.suffix}`;
        const active = pathname.startsWith(href);
        return (
          <Link
            key={link.key}
            href={href}
            className={[
              "inline-flex min-h-11 items-center rounded px-4 text-sm font-medium",
              active
                ? "bg-primary text-surface"
                : "border border-border bg-surface text-text hover:bg-bg-2",
            ].join(" ")}
          >
            {t(link.key)}
            {link.key === "requests" && requestBadge > 0 ? (
              <span className="ml-2 rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">
                {requestBadge}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
