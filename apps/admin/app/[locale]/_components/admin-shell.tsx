"use client";

import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { resolveAdminRoleKind, useAdminIdentity } from "../../../lib/admin-identity";
import { resolveAdminNavCapabilities } from "../../../lib/admin-nav-capabilities";
import { isAdminPasswordRecoveryPath } from "../../../lib/password-recovery-path";
import {
  type AdminPermissions,
  AdminPermissionRefreshContext,
  AdminPermissionsContext,
  useAdminPermissionCheck,
} from "../../../lib/roles-api";

import { AdminAccountMenu } from "./admin-account-menu";
import { AdminCommandPalette } from "./admin-command-palette";
import { AdminDensityProvider } from "./admin-density";
import { AdminDensityToggle } from "./admin-density-toggle";
import {
  ADMIN_NAV_GROUPS,
  ADMIN_EXPLICIT_GRANT_ITEMS,
  adminItemHref,
  adminRouteAllowedByAlternateItem,
  filterAdminNavGroups,
  flattenAdminNavItems,
  resolveAdminActiveGroup,
  resolveAdminActiveItem,
} from "./admin-nav-config";
import { AdminNavIcon } from "./admin-nav-icon";
import { AdminNotificationBell } from "./admin-notification-bell";
import { usePendingProductModerationCount } from "./use-pending-product-count";

type AdminShellProps = {
  locale: string;
  children: React.ReactNode;
};

function navLinkClass(active: boolean, compact = false): string {
  return [
    "inline-flex items-center gap-2 rounded-md border text-sm transition-colors press-scale",
    compact ? "min-h-11 shrink-0 px-3 font-medium" : "min-h-11 w-full px-2",
    active
      ? "border-primary bg-primary/10 font-semibold text-primary"
      : "border-transparent font-medium text-text hover:border-border hover:bg-bg-2 hover:text-primary",
  ].join(" ");
}

export function AdminShell({ locale, children }: AdminShellProps) {
  const pathname = usePathname();
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const menuId = useId();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // The sidebar must survive route changes: permissions reload on every navigation
  // (grants go null for a moment), which used to empty the nav and reset its scroll.
  // Keep the last known grants for the nav only, and only while moving to another route;
  // page content still waits for fresh ones, and a same-route revalidation (focus, auth
  // event) still clears everything so a revoked grant disappears at once.
  const [navGrants, setNavGrants] = useState<{
    grants: AdminPermissions;
    route: string;
  } | null>(null);
  const navScrollRef = useRef<HTMLElement>(null);
  const navScrollTopRef = useRef(0);
  const mainRef = useRef<HTMLElement>(null);

  const rest = pathname.replace(/^\/[^/]+/, "") || "/";
  const isBareAuthRoute =
    rest === "/login" ||
    rest.startsWith("/login/") ||
    isAdminPasswordRecoveryPath(pathname) ||
    rest === "/permission-denied";
  const {
    grants,
    refresh,
    error: grantError,
  } = useAdminPermissionCheck(isBareAuthRoute ? null : pathname);

  useEffect(() => {
    if (grants) {
      setNavGrants({ grants, route: pathname });
    }
  }, [grants, pathname]);

  useEffect(() => {
    if (isBareAuthRoute) {
      setNavGrants(null);
    }
  }, [isBareAuthRoute]);

  // Belt and braces: put the sidebar back where the admin left it after any re-render.
  useLayoutEffect(() => {
    const nav = navScrollRef.current;
    if (nav && nav.scrollTop !== navScrollTopRef.current) {
      nav.scrollTop = navScrollTopRef.current;
    }
  });

  // Main content scrolls on its own, so a new page must start at its top.
  useLayoutEffect(() => {
    if (mainRef.current) {
      mainRef.current.scrollTop = 0;
    }
  }, [pathname]);

  const identity = useAdminIdentity(!isBareAuthRoute, grants);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen || isBareAuthRoute) {
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
  }, [menuOpen, isBareAuthRoute]);

  const navSource = isBareAuthRoute
    ? null
    : (grants ??
      (navGrants && !grantError && navGrants.route !== pathname ? navGrants.grants : null));
  const pendingProducts = usePendingProductModerationCount(navSource);

  if (isBareAuthRoute) {
    return <>{children}</>;
  }

  const roleKind = resolveAdminRoleKind(navSource);
  const capabilities = resolveAdminNavCapabilities(
    navSource?.permissions ?? [],
    navSource?.unrestricted ?? false,
    navSource?.can_manage_roles ?? false,
  );
  const navGroups = filterAdminNavGroups(capabilities, ADMIN_NAV_GROUPS);
  const visibleItems = flattenAdminNavItems(navGroups);

  const activeKey = resolveAdminActiveItem(rest, visibleItems);
  const activeGroup = resolveAdminActiveGroup(rest, navGroups);
  const requested = resolveAdminActiveItem(rest);
  // Personal, role-scoped surfaces every admin may open (the API filters to
  // the caller's own rows), so they are not gated by nav permissions.
  const isPersonalRoute = rest === "/notifications";
  const denied =
    !isPersonalRoute &&
    ((requested !== undefined &&
      ADMIN_EXPLICIT_GRANT_ITEMS.has(requested) &&
      !capabilities[requested]) ||
      (!grants?.unrestricted &&
        (!requested ||
          (!capabilities[requested] && !adminRouteAllowedByAlternateItem(rest, capabilities)) ||
          rest.startsWith("/moderation/flags"))));

  const chrome = (
    <div className="flex h-dvh flex-col overflow-hidden bg-bg text-text">
      <header className="shrink-0 border-b border-border bg-panel text-panel-text">
        <div className="flex w-full items-center justify-between gap-3 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="hidden sm:block">
              <AdminNavIcon itemKey="home" size={40} />
            </span>
            <div className="min-w-0">
              <h1 className="truncate font-display text-lg font-semibold tracking-tight text-panel-text">
                {t("title")}
              </h1>
              <p className="hidden truncate text-xs text-panel-muted sm:block">
                {t("shell.eyebrow")} · {t("shell.environment")}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <AdminCommandPalette locale={locale} />
            <span className="hidden sm:block">
              <AdminDensityToggle />
            </span>
            <AdminNotificationBell locale={locale} />
            <ThemeToggle
              label={tCommon("theme.label")}
              lightLabel={tCommon("theme.light")}
              darkLabel={tCommon("theme.dark")}
              systemLabel={tCommon("theme.system")}
              className="!border-panel-muted/40 !bg-transparent !text-panel-text hover:!border-panel-text"
            />
            <AdminAccountMenu locale={locale} identity={identity} roleKind={roleKind} />
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <nav
          ref={navScrollRef}
          aria-label={t("shell.navAriaLabel")}
          data-testid="admin-sidebar"
          onScroll={(event) => {
            // An emptied nav clamps to 0; do not let that overwrite where the admin was.
            if (navGroups.length > 0) {
              navScrollTopRef.current = event.currentTarget.scrollTop;
            }
          }}
          className="hidden shrink-0 overflow-y-auto overscroll-contain border-r border-border bg-surface px-2 py-2 lg:block lg:w-56"
        >
          <div className="space-y-3">
            {navGroups.map((group) => (
              <section key={group.key}>
                <h2 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-text-3">
                  {t(`nav.groups.${group.key}` as "nav.groups.overview")}
                </h2>
                <ul className="space-y-0.5">
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
                          <AdminNavIcon itemKey={item.key} size={32} />
                          <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                            <span className="truncate">{t(`nav.${item.key}` as "nav.home")}</span>
                            {item.key === "moderation" &&
                            typeof pendingProducts === "number" &&
                            pendingProducts > 0 ? (
                              <span
                                className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-[var(--primary-btn-fg)]"
                                aria-label={t("nav.moderationPendingBadge", {
                                  count: pendingProducts,
                                })}
                              >
                                {pendingProducts}
                              </span>
                            ) : null}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        </nav>

        <div className="shrink-0 border-b border-border px-3 py-2 lg:hidden">
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
            {capabilities.orders ? (
              <Link
                href={adminItemHref(locale, "orders")}
                className={navLinkClass(activeKey === "orders", true)}
              >
                {t("nav.orders")}
              </Link>
            ) : null}
            {capabilities.kyc ? (
              <Link
                href={adminItemHref(locale, "kyc")}
                className={navLinkClass(activeKey === "kyc", true)}
              >
                {t("nav.kyc")}
              </Link>
            ) : null}
          </div>
        </div>

        <main
          ref={mainRef}
          data-testid="admin-main"
          className="admin-main min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain bg-bg px-3 py-4 sm:px-4"
        >
          {grantError ? (
            <p role="alert" className="animate-page-in text-sm text-danger">
              {t("shell.permissionError")}
            </p>
          ) : !grants ? (
            <p role="status" className="animate-page-in text-sm text-muted">
              {t("shell.permissionChecking")}
            </p>
          ) : denied ? (
            <p role="alert" className="animate-page-in text-sm text-danger">
              {t("shell.permissionDenied")}
            </p>
          ) : (
            children
          )}
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
            {navGroups.map((group) => (
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

  // Keep provider wrappers mounted across permission reloads so the sidebar DOM
  // (ref + scroll) survives route changes while grants are null.
  return (
    <AdminDensityProvider>
      <AdminPermissionsContext.Provider value={grants}>
        <AdminPermissionRefreshContext.Provider value={refresh}>
          {chrome}
        </AdminPermissionRefreshContext.Provider>
      </AdminPermissionsContext.Provider>
    </AdminDensityProvider>
  );
}
