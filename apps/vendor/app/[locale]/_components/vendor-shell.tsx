"use client";

import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { VendorQuickNav } from "./vendor-quick-nav";

type VendorShellProps = {
  locale: string;
  children: React.ReactNode;
};

/**
 * Authenticated vendor chrome. A branded header (wordmark + theme toggle) shows
 * on every route except the login page (which supplies its own standalone
 * chrome — so mounting the header there would double it up). The primary
 * VendorQuickNav shows on the dashboard, but is hidden on login and onboarding,
 * where its links would dead-end for a user who doesn't yet hold the vendor
 * role. Active-route highlighting comes from the pathname, hence a client shell.
 */
export function VendorShell({ locale, children }: VendorShellProps) {
  const pathname = usePathname();
  const tCommon = useTranslations("common");

  // usePathname carries the locale prefix but not the (auth) route group.
  const rest = pathname.replace(/^\/[^/]+/, "") || "/";
  if (rest === "/login" || rest.startsWith("/login/")) {
    return <>{children}</>;
  }

  const isOnboarding = rest === "/onboarding" || rest.startsWith("/onboarding/");
  const active =
    rest === "/"
      ? ("home" as const)
      : rest.startsWith("/listings")
        ? ("listings" as const)
        : rest.startsWith("/orders")
          ? ("orders" as const)
          : rest.startsWith("/profile")
            ? ("profile" as const)
            : undefined;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-2">
        <Link href={`/${locale}`} className="font-display text-base font-semibold text-display-ink">
          {tCommon("app.name")}
        </Link>
        <ThemeToggle
          label={tCommon("theme.label")}
          lightLabel={tCommon("theme.light")}
          darkLabel={tCommon("theme.dark")}
          systemLabel={tCommon("theme.system")}
        />
      </header>
      {isOnboarding ? null : <VendorQuickNav locale={locale} active={active} />}
      <div className="flex-1">{children}</div>
    </div>
  );
}
