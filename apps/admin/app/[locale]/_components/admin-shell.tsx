"use client";

import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import {
  ADMIN_NAV_GROUPS,
  adminItemHref,
  resolveAdminActiveGroup,
  resolveAdminActiveItem,
} from "./admin-nav-config";
import { SignOutButton } from "./sign-out-button";

type AdminShellProps = {
  locale: string;
  children: React.ReactNode;
};

function navLinkClass(active: boolean, compact = false): string {
  return [
    "inline-flex min-h-11 items-center rounded-md border text-sm font-medium",
    compact ? "shrink-0 px-3" : "w-full px-3",
    active
      ? "border-primary bg-surface text-primary"
      : "border-border bg-surface text-text hover:border-primary hover:text-primary",
  ].join(" ");
}

export function AdminShell({ locale, children }: AdminShellProps) {
  const pathname = usePathname();
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const menuId = useId();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const rest = pathname.replace(/^\/[^/]+/, "") || "/";
  if (rest === "/login" || rest.startsWith("/login/")) {
    return <>{children}</>;
  }

  const activeKey = resolveAdminActiveItem(rest);
  const activeGroup = resolveAdminActiveGroup(rest);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

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
        <nav aria-label={t("shell.navAriaLabel")} className="hidden shrink-0 lg:block lg:w-60">
          <div className="sticky top-4 space-y-5">
            {ADMIN_NAV_GROUPS.map((group) => (
              <section key={group.key}>
                <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-text-3">
                  {t(`nav.groups.${group.key}` as "nav.groups.overview")}
                </h2>
                <ul className="space-y-1">
                  {group.items.map((item) => {
                    const href = adminItemHref(locale, item.href);
                    const active = activeKey === item.key;
                    return (
                      <li key={item.key}>
                        <Link
                          href={href}
                          aria-current={active ? "page" : undefined}
                          className={navLinkClass(active)}
                        >
                          {t(`nav.${item.key}` as "nav.home")}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        </nav>

        <div className="lg:hidden">
          <div className="flex items-center gap-2">
            <button
              ref={menuButtonRef}
              type="button"
              className="inline-flex min-h-11 flex-1 items-center justify-between rounded-md border border-border bg-surface px-3 text-sm font-medium text-text"
              aria-expanded={menuOpen}
              aria-controls={menuId}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span>{t("shell.mobileNavLabel")}</span>
              <span className="text-xs text-muted">
                {activeGroup
                  ? t(`nav.groups.${activeGroup}` as "nav.groups.overview")
                  : t("nav.home")}
              </span>
            </button>
            <Link
              href={adminItemHref(locale, "orders")}
              className={navLinkClass(activeKey === "orders", true)}
            >
              {t("nav.orders")}
            </Link>
            <Link
              href={adminItemHref(locale, "kyc")}
              className={navLinkClass(activeKey === "kyc", true)}
            >
              {t("nav.kyc")}
            </Link>
          </div>
        </div>

        <main className="min-w-0 flex-1 rounded-lg border border-border bg-surface p-4 shadow-sm">
          {children}
        </main>
      </div>

      {menuOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 lg:hidden"
          role="presentation"
          onClick={() => setMenuOpen(false)}
        >
          <div
            id={menuId}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${menuId}-title`}
            className="max-h-[85dvh] w-full overflow-y-auto rounded-t-2xl border border-border bg-surface p-4 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="mb-4 flex items-center justify-between gap-2">
              <h2 id={`${menuId}-title`} className="text-base font-semibold text-text">
                {t("shell.mobileMenuTitle")}
              </h2>
              <button
                type="button"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-3 text-sm"
                onClick={() => setMenuOpen(false)}
              >
                {t("shell.mobileMenuClose")}
              </button>
            </header>
            {ADMIN_NAV_GROUPS.map((group) => (
              <section key={group.key} className="mb-4 last:mb-0">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">
                  {t(`nav.groups.${group.key}` as "nav.groups.overview")}
                </h3>
                <ul className="grid grid-cols-2 gap-2">
                  {group.items.map((item) => {
                    const href = adminItemHref(locale, item.href);
                    const active = activeKey === item.key;
                    return (
                      <li key={item.key}>
                        <Link
                          href={href}
                          aria-current={active ? "page" : undefined}
                          className={navLinkClass(active, true)}
                          onClick={() => setMenuOpen(false)}
                        >
                          {t(`nav.${item.key}` as "nav.home")}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
