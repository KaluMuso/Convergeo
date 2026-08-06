"use client";

import { BottomNav, type BottomNavItem } from "@vergeo/ui/src/bottom-nav";
import { IconCategories, IconHome, IconOrders } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import {
  isVendorMoreMenuActive,
  resolveVendorActiveItem,
  VENDOR_MOBILE_PRIMARY,
  VENDOR_MORE_MENU_KEY,
  VENDOR_NAV_GROUPS,
  vendorItemHref,
} from "./vendor-nav-config";

type VendorNavProps = {
  locale: string;
};

function IconMore() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      aria-hidden
      className="h-5 w-5 shrink-0"
    >
      <path d="M5 7h14M5 12h14M5 17h14" />
    </svg>
  );
}

const MOBILE_ICONS: Record<string, React.ReactNode> = {
  home: <IconHome />,
  orders: <IconOrders />,
  listings: <IconCategories />,
  more: <IconMore />,
};

function navLinkClass(active: boolean): string {
  return [
    "inline-flex min-h-11 w-full items-center rounded-md px-3 text-sm font-medium",
    active
      ? "bg-primary text-[var(--primary-btn-fg)]"
      : "text-text-2 hover:bg-bg-2 hover:text-text",
  ].join(" ");
}

export function VendorNav({ locale }: VendorNavProps) {
  const pathname = usePathname();
  const t = useTranslations("vendor");
  const menuId = useId();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const rest = pathname.replace(/^\/[^/]+/, "") || "/";
  const activeKey = resolveVendorActiveItem(rest);
  const moreActive = isVendorMoreMenuActive(rest);

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

  const mobileItems: BottomNavItem[] = VENDOR_MOBILE_PRIMARY.map((key) => {
    if (key === VENDOR_MORE_MENU_KEY) {
      return {
        key,
        icon: MOBILE_ICONS.more,
        label: t("shell.nav.more"),
        href: "#",
        active: moreActive,
      };
    }
    const item = VENDOR_NAV_GROUPS.flatMap((g) => g.items).find((entry) => entry.key === key)!;
    return {
      key,
      icon: MOBILE_ICONS[key],
      label: t(`shell.nav.${key}` as "shell.nav.home"),
      href: vendorItemHref(locale, item.href),
      active: activeKey === key,
    };
  });

  return (
    <>
      <nav
        aria-label={t("shell.nav.desktopAriaLabel")}
        className="hidden w-56 shrink-0 border-r border-border bg-surface lg:block"
      >
        <div className="sticky top-0 max-h-dvh overflow-y-auto px-3 py-4">
          {VENDOR_NAV_GROUPS.map((group) => (
            <section key={group.key} className="mb-5 last:mb-0">
              <h2 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-text-3">
                {t(`shell.groups.${group.key}` as "shell.groups.operate")}
              </h2>
              <ul className="space-y-1">
                {group.items.map((item) => {
                  const href = vendorItemHref(locale, item.href);
                  const active = activeKey === item.key;
                  return (
                    <li key={item.key}>
                      <Link
                        href={href}
                        aria-current={active ? "page" : undefined}
                        className={navLinkClass(active)}
                      >
                        {t(`shell.nav.${item.key}` as "shell.nav.home")}
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
        <BottomNav
          items={mobileItems}
          ariaLabel={t("shell.nav.ariaLabel")}
          LinkComponent={({ href, children, className, ...rest }) => {
            if (href === "#") {
              return (
                <button
                  ref={menuButtonRef}
                  type="button"
                  className={className}
                  aria-expanded={menuOpen}
                  aria-controls={menuId}
                  onClick={() => setMenuOpen((open) => !open)}
                  {...rest}
                >
                  {children}
                </button>
              );
            }
            return (
              <Link href={href} className={className} {...rest}>
                {children}
              </Link>
            );
          }}
          desktopHiddenClassName="lg:hidden"
        />
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
            className="max-h-[80dvh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-border bg-surface p-4 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="mb-4 flex items-center justify-between gap-2">
              <h2 id={`${menuId}-title`} className="text-base font-semibold text-text">
                {t("shell.moreMenu.title")}
              </h2>
              <button
                type="button"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-3 text-sm"
                onClick={() => setMenuOpen(false)}
              >
                {t("shell.moreMenu.close")}
              </button>
            </header>
            {VENDOR_NAV_GROUPS.map((group) => (
              <section key={group.key} className="mb-4 last:mb-0">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-3">
                  {t(`shell.groups.${group.key}` as "shell.groups.operate")}
                </h3>
                <ul className="grid grid-cols-2 gap-2">
                  {group.items.map((item) => {
                    const href = vendorItemHref(locale, item.href);
                    const active = activeKey === item.key;
                    return (
                      <li key={item.key}>
                        <Link
                          href={href}
                          aria-current={active ? "page" : undefined}
                          className={[
                            "inline-flex min-h-11 w-full items-center rounded-md border px-3 text-sm font-medium",
                            active
                              ? "border-primary bg-primary/10 text-primary"
                              : "border-border bg-bg text-text hover:border-primary",
                          ].join(" ")}
                          onClick={() => setMenuOpen(false)}
                        >
                          {t(`shell.nav.${item.key}` as "shell.nav.home")}
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
    </>
  );
}
