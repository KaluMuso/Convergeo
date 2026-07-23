"use client";

import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { SignOutButton } from "./sign-out-button";

const NAV_ITEMS = [
  { href: "", key: "home" },
  { href: "kyc", key: "kyc" },
  { href: "business", key: "business" },
  { href: "moderation", key: "moderation" },
  { href: "disputes", key: "disputes" },
  { href: "orders", key: "orders" },
  { href: "config", key: "config" },
  { href: "merch", key: "merch" },
  { href: "translations", key: "translations" },
  { href: "support", key: "support" },
] as const;

type AdminShellProps = {
  locale: string;
  children: React.ReactNode;
};

/**
 * Authenticated admin chrome (header + sidebar + sign-out), rendered around
 * every route EXCEPT the login page. Gating on the pathname keeps the
 * privileged sidebar and the Sign Out button from rendering before
 * authentication — the (auth)/login page supplies its own standalone chrome,
 * so pre-auth it must stand alone. Active-route highlighting is derived from
 * the pathname (only available client-side, hence this component).
 */
export function AdminShell({ locale, children }: AdminShellProps) {
  const pathname = usePathname();
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");

  // usePathname carries the locale prefix but not the (auth) route group,
  // so the login route resolves to `/login` regardless of locale.
  const rest = pathname.replace(/^\/[^/]+/, "") || "/";
  if (rest === "/login" || rest.startsWith("/login/")) {
    return <>{children}</>;
  }

  const isActive = (href: string) =>
    href ? rest === `/${href}` || rest.startsWith(`/${href}/`) : rest === "/";

  return (
    <div className="min-h-dvh bg-bg text-text">
      <header className="border-b border-border bg-panel text-panel-text">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-wide text-panel-muted">{t("shell.eyebrow")}</p>
            <h1 className="font-serif text-xl text-panel-text">{t("title")}</h1>
            <p className="text-xs text-panel-muted">{t("shell.environment")}</p>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle
              label={tCommon("theme.label")}
              lightLabel={tCommon("theme.light")}
              darkLabel={tCommon("theme.dark")}
              systemLabel={tCommon("theme.system")}
              className="border-panel-muted/40 bg-transparent text-panel-text hover:border-panel-text hover:text-panel-text"
            />
            <SignOutButton
              locale={locale}
              label={t("shell.signOut")}
              className="inline-flex min-h-11 items-center justify-center rounded-md border border-panel-muted/40 px-4 text-sm font-medium text-panel-text disabled:opacity-60"
            />
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-4 lg:flex-row">
        <nav
          aria-label={t("title")}
          className="flex shrink-0 flex-row gap-2 overflow-x-auto lg:w-56 lg:flex-col lg:overflow-visible"
        >
          {NAV_ITEMS.map((item) => {
            const href = item.href ? `/${locale}/${item.href}` : `/${locale}`;
            const active = isActive(item.href);
            return (
              <Link
                key={item.key}
                aria-current={active ? "page" : undefined}
                className={`inline-flex min-h-11 shrink-0 items-center rounded-md border px-3 text-sm font-medium ${
                  active
                    ? "border-primary bg-surface text-primary"
                    : "border-border bg-surface text-text hover:border-primary hover:text-primary"
                }`}
                href={href}
              >
                {t(`nav.${item.key}`)}
              </Link>
            );
          })}
        </nav>

        <main className="min-w-0 flex-1 rounded-lg border border-border bg-surface p-4 shadow-sm">
          {children}
        </main>
      </div>
    </div>
  );
}
