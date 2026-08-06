"use client";

import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { VendorNav } from "./vendor-nav";

type VendorShellProps = {
  locale: string;
  children: React.ReactNode;
};

/**
 * Authenticated vendor chrome. Login and onboarding routes render bare children;
 * all other routes get a responsive shell (desktop sidebar + mobile bottom nav).
 */
export function VendorShell({ locale, children }: VendorShellProps) {
  const pathname = usePathname();
  const tCommon = useTranslations("common");

  const rest = pathname.replace(/^\/[^/]+/, "") || "/";
  if (rest === "/login" || rest.startsWith("/login/")) {
    return <>{children}</>;
  }

  const isOnboarding = rest === "/onboarding" || rest.startsWith("/onboarding/");

  if (isOnboarding) {
    return (
      <div className="flex min-h-dvh flex-col">
        <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-2">
          <Link
            href={`/${locale}`}
            className="font-display text-base font-semibold text-display-ink"
          >
            {tCommon("app.name")}
          </Link>
          <ThemeToggle
            label={tCommon("theme.label")}
            lightLabel={tCommon("theme.light")}
            darkLabel={tCommon("theme.dark")}
            systemLabel={tCommon("theme.system")}
          />
        </header>
        <div className="flex-1">{children}</div>
      </div>
    );
  }

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

      <div className="flex min-h-0 flex-1">
        <VendorNav locale={locale} />
        <div className="min-w-0 flex-1 overflow-x-hidden pb-[calc(3.5rem+env(safe-area-inset-bottom,0px))] lg:pb-0">
          {children}
        </div>
      </div>
    </div>
  );
}
