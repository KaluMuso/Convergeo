"use client";

import { glassClass } from "@vergeo/ui/src/glass";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { resolveAdminNavCapabilities } from "../../../lib/admin-nav-capabilities";
import { useAdminPermissions } from "../../../lib/roles-api";

import {
  ADMIN_NAV_GROUPS,
  adminItemHref,
  filterAdminNavGroups,
  flattenAdminNavItems,
  type AdminNavItem,
} from "./admin-nav-config";
import { AdminNavIcon } from "./admin-nav-icon";

type AdminCommandPaletteProps = {
  locale: string;
};

export function AdminCommandPalette({ locale }: AdminCommandPaletteProps) {
  const t = useTranslations("admin");
  const tPalette = useTranslations("admin.shell.commandPalette");
  const pathname = usePathname();
  const grants = useAdminPermissions();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogId = useId();

  const items = useMemo(() => {
    if (!grants) {
      return [] as AdminNavItem[];
    }
    const capabilities = resolveAdminNavCapabilities(
      grants.permissions,
      grants.unrestricted,
      grants.can_manage_roles,
    );
    return flattenAdminNavItems(filterAdminNavGroups(capabilities, ADMIN_NAV_GROUPS));
  }, [grants]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return items;
    }
    return items.filter((item) => {
      const label = t(`nav.${item.key}` as "nav.home").toLowerCase();
      return label.includes(q) || item.href.toLowerCase().includes(q);
    });
  }, [items, query, t]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close]);

  useEffect(() => {
    if (open) {
      const timer = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    close();
  }, [pathname, close]);

  if (!grants) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        className="hidden min-h-11 items-center gap-2 rounded-md border border-panel-muted/40 bg-transparent px-3 text-xs text-panel-muted transition-transform press-scale hover:border-panel-text hover:text-panel-text focus-visible:outline-none focus-visible:shadow-focusRing sm:inline-flex"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        data-testid="admin-command-palette-open"
      >
        <span>{tPalette("open")}</span>
        <kbd className="rounded border border-panel-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
          {tPalette("shortcut")}
        </kbd>
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-4 pt-[12vh] backdrop-blur-[2px]"
          role="presentation"
          onClick={close}
        >
          <div
            id={dialogId}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${dialogId}-title`}
            className={`${glassClass("overlay")} animate-page-in w-full max-w-lg overflow-hidden rounded-xl`}
            onClick={(event) => event.stopPropagation()}
            data-testid="admin-command-palette"
          >
            <header className="border-b border-border px-4 py-3">
              <h2 id={`${dialogId}-title`} className="sr-only">
                {tPalette("title")}
              </h2>
              <input
                ref={inputRef}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={tPalette("placeholder")}
                className="w-full min-h-11 border-0 bg-transparent text-sm text-text outline-none placeholder:text-muted"
                autoComplete="off"
                aria-label={tPalette("placeholder")}
              />
              <p className="mt-1 text-xs text-muted">{tPalette("hint")}</p>
            </header>
            <ul className="max-h-[50vh] list-none overflow-y-auto p-2" role="listbox">
              {filtered.length === 0 ? (
                <li className="px-3 py-6 text-center text-sm text-muted">
                  {tPalette("noResults")}
                </li>
              ) : (
                filtered.map((item) => (
                  <li key={item.key}>
                    <Link
                      href={adminItemHref(locale, item.href)}
                      role="option"
                      className="flex min-h-11 items-center gap-3 rounded-lg px-2 py-2 text-sm text-text no-underline transition-colors hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
                      onClick={close}
                    >
                      <AdminNavIcon itemKey={item.key} size={32} />
                      <span className="font-medium">{t(`nav.${item.key}` as "nav.home")}</span>
                    </Link>
                  </li>
                ))
              )}
            </ul>
            <footer className="flex justify-end border-t border-border px-3 py-2">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md px-3 text-xs text-muted press-scale"
                onClick={close}
              >
                {tPalette("close")}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </>
  );
}
