"use client";

import { glassClass } from "@vergeo/ui/src/glass";
import { useFocusTrap, useScrollLock } from "@vergeo/ui/src/modal";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useSession } from "../../../../../lib/customer-session";

import { recordBrowsedCategory } from "./browsed-categories";
import { fillName, type MegaMenuLabels } from "./labels";
import { IconChevronLeft, IconChevronRight, IconClose } from "./menu-icons";
import { buildMenuModel, type MenuDept, type MenuLink } from "./nav-model";
import { useMenuTree } from "./use-menu-tree";

import type { NavCategory } from "../category-tree";

/** Departments shown before "See all"; sub-lists collapse past SUB_COLLAPSED. */
export const DEPT_COLLAPSED = 5;
export const SUB_COLLAPSED = 8;

export type MobileDrawerProps = {
  locale: string;
  labels: MegaMenuLabels;
  onClose: () => void;
  loadCategories?: () => Promise<NavCategory[]>;
};

const rowClass =
  "flex min-h-12 w-full touch-manipulation items-center justify-between gap-3 px-4 text-left text-sm text-text transition-colors hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing";

function SectionHeading({ children }: { children: string }) {
  return (
    <h3 className="px-4 pb-1 pt-4 font-display text-base font-bold text-display-ink">{children}</h3>
  );
}

function userDisplayName(user: { email?: string | null; user_metadata?: unknown } | null): string {
  if (!user) {
    return "";
  }
  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  for (const key of ["full_name", "name"]) {
    const value = meta[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return user.email?.split("@")[0] ?? "";
}

/**
 * Phones/tablets (< lg): Amazon-style left drawer with a drill-down.
 * Main menu → tap a department → the sub-list slides in with a "Main menu"
 * back row. Focus is trapped, Escape closes, background scroll is locked.
 */
export default function MobileDrawer({
  locale,
  labels,
  onClose,
  loadCategories,
}: MobileDrawerProps) {
  const pathname = usePathname();
  const firstPathRef = useRef(pathname);
  const drawerRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<string | null>(null);
  const { user } = useSession();
  const { tree, loading } = useMenuTree(true, labels.fallbackRoots, loadCategories);

  const [drillId, setDrillId] = useState<string | null>(null);
  const [showAllDepts, setShowAllDepts] = useState(false);
  const [showAllSubs, setShowAllSubs] = useState(false);

  useEffect(() => {
    if (pathname !== firstPathRef.current) {
      onClose();
    }
  }, [pathname, onClose]);

  useScrollLock(true);
  useFocusTrap(drawerRef, true, onClose);

  const model = useMemo(
    () => (tree ? buildMenuModel(tree, labels, locale) : null),
    [tree, labels, locale],
  );
  const drillDepts = useMemo<MenuDept[]>(
    () => (model ? [...model.products, model.services, model.events] : []),
    [model],
  );
  const drill = drillId ? (drillDepts.find((dept) => dept.id === drillId) ?? null) : null;

  // Move focus with the slide: into the drill-down's back row, and back to the
  // department that opened it on return.
  const prevDrillRef = useRef<string | null>(null);
  useEffect(() => {
    if (drill && prevDrillRef.current === null) {
      backRef.current?.focus({ preventScroll: true });
    } else if (!drill && prevDrillRef.current !== null && openerRef.current) {
      Array.from(drawerRef.current?.querySelectorAll<HTMLElement>("[data-dept-id]") ?? [])
        .find((el) => el.dataset.deptId === openerRef.current)
        ?.focus({ preventScroll: true });
    }
    prevDrillRef.current = drill ? drill.id : null;
  }, [drill]);

  const openDept = (dept: MenuDept) => {
    openerRef.current = dept.id;
    setShowAllSubs(false);
    setDrillId(dept.id);
  };

  const navigate = (link: MenuLink) => () => {
    recordBrowsedCategory({ slug: link.slug, label: link.label, href: link.href });
    onClose();
  };

  const signedInName = userDisplayName(user);
  const greeting = user
    ? fillName(labels.helloUser, signedInName || labels.account)
    : labels.helloGuest;

  const products = model?.products ?? [];
  const visibleDepts = showAllDepts ? products : products.slice(0, DEPT_COLLAPSED);
  const drillChildren = drill?.children ?? [];
  const visibleSubs = showAllSubs ? drillChildren : drillChildren.slice(0, SUB_COLLAPSED);

  const deptRow = (dept: MenuDept) =>
    dept.children.length > 0 ? (
      <button
        type="button"
        data-dept-id={dept.id}
        onClick={() => openDept(dept)}
        className={rowClass}
      >
        <span className="min-w-0 truncate">{dept.label}</span>
        <IconChevronRight className="shrink-0 text-text-3" />
      </button>
    ) : (
      <Link href={dept.href} data-dept-id={dept.id} onClick={navigate(dept)} className={rowClass}>
        <span className="min-w-0 truncate">{dept.label}</span>
      </Link>
    );

  const hidden = { inert: true, "aria-hidden": true } as const;

  const body = (
    <div data-testid="mobile-drawer-root">
      <div
        data-testid="mobile-drawer-scrim"
        aria-hidden="true"
        onClick={onClose}
        className="fixed inset-0 z-[70]"
        style={{ backgroundColor: "color-mix(in srgb, var(--panel) 55%, transparent)" }}
      />
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={labels.drawerAria}
        tabIndex={-1}
        className={`${glassClass("overlay")} fixed inset-y-0 left-0 z-[71] flex w-[min(20.5rem,calc(100vw-2.5rem))] max-w-full flex-col overflow-hidden rounded-r-lg`}
      >
        <div className="flex min-h-14 shrink-0 items-center justify-between gap-2 border-b border-border bg-primary px-4 text-[var(--primary-btn-fg)]">
          {user ? (
            <Link
              href={`/${locale}/account`}
              onClick={onClose}
              className="inline-flex min-h-11 min-w-0 flex-1 items-center truncate rounded-sm font-display text-base font-bold focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {greeting}
            </Link>
          ) : (
            <Link
              href={`/${locale}/login`}
              onClick={onClose}
              aria-label={`${labels.helloGuest}. ${labels.signIn}`}
              className="inline-flex min-h-11 min-w-0 flex-1 items-center truncate rounded-sm font-display text-base font-bold focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {greeting}
            </Link>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label={labels.close}
            className="inline-flex size-11 shrink-0 touch-manipulation items-center justify-center rounded focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            <IconClose />
          </button>
        </div>

        <div className="relative min-h-0 flex-1 overflow-hidden">
          <div
            data-testid="mobile-drawer-track"
            data-view={drill ? "drill" : "main"}
            className={`flex h-full w-[200%] transition-transform duration-page ease-out motion-reduce:transition-none ${
              drill ? "-translate-x-1/2" : "translate-x-0"
            }`}
          >
            <div
              data-testid="mobile-drawer-main"
              className="h-full w-1/2 overflow-y-auto overscroll-contain pb-6"
              {...(drill ? hidden : {})}
            >
              <SectionHeading>{labels.shopByDepartment}</SectionHeading>
              {loading || model === null ? (
                <p className="px-4 py-3 text-sm text-text-2">{labels.loading}</p>
              ) : products.length === 0 ? (
                <p className="px-4 py-3 text-sm text-text-2">{labels.empty}</p>
              ) : (
                <ul className="m-0 list-none p-0">
                  {visibleDepts.map((dept) => (
                    <li key={dept.id}>{deptRow(dept)}</li>
                  ))}
                  {products.length > DEPT_COLLAPSED ? (
                    <li>
                      <button
                        type="button"
                        aria-expanded={showAllDepts}
                        onClick={() => setShowAllDepts((value) => !value)}
                        className={`${rowClass} font-medium text-primary`}
                      >
                        {showAllDepts ? labels.seeLess : labels.seeAll}
                      </button>
                    </li>
                  ) : null}
                </ul>
              )}

              <div className="mt-2 border-t border-border">
                <ul className="m-0 list-none p-0 pt-2">
                  {model ? (
                    <>
                      <li>{deptRow(model.services)}</li>
                      <li>{deptRow(model.events)}</li>
                    </>
                  ) : null}
                  <li>
                    <Link href={`/${locale}/deals`} onClick={onClose} className={rowClass}>
                      {labels.deals}
                    </Link>
                  </li>
                  <li>
                    <Link href={`/${locale}/sell`} onClick={onClose} className={rowClass}>
                      {labels.sell}
                    </Link>
                  </li>
                </ul>
              </div>

              <div className="mt-2 border-t border-border">
                <SectionHeading>{labels.helpSettings}</SectionHeading>
                <ul className="m-0 list-none p-0">
                  <li>
                    <Link href={`/${locale}/account`} onClick={onClose} className={rowClass}>
                      {labels.account}
                    </Link>
                  </li>
                  <li>
                    <Link href={`/${locale}/account/orders`} onClick={onClose} className={rowClass}>
                      {labels.orders}
                    </Link>
                  </li>
                  <li>
                    <Link href={`/${locale}/help`} onClick={onClose} className={rowClass}>
                      {labels.help}
                    </Link>
                  </li>
                </ul>
              </div>
            </div>

            <div
              data-testid="mobile-drawer-drill"
              className="h-full w-1/2 overflow-y-auto overscroll-contain pb-6"
              {...(drill ? {} : hidden)}
            >
              <button
                ref={backRef}
                type="button"
                disabled={!drill}
                onClick={() => setDrillId(null)}
                className={`${rowClass} justify-start border-b border-border font-medium`}
              >
                <IconChevronLeft className="shrink-0" />
                <span>{labels.mainMenu}</span>
              </button>
              {drill ? (
                <>
                  <h2 className="px-4 pb-1 pt-4 font-display text-base font-bold text-display-ink">
                    {drill.label}
                  </h2>
                  <ul className="m-0 list-none p-0">
                    <li>
                      <Link
                        href={drill.href}
                        onClick={navigate(drill)}
                        className={`${rowClass} font-medium text-primary`}
                      >
                        {fillName(labels.allIn, drill.label)}
                      </Link>
                    </li>
                    {visibleSubs.map((child) => (
                      <li key={child.id}>
                        <Link href={child.href} onClick={navigate(child)} className={rowClass}>
                          <span className="min-w-0 truncate">{child.label}</span>
                        </Link>
                      </li>
                    ))}
                    {drillChildren.length > SUB_COLLAPSED ? (
                      <li>
                        <button
                          type="button"
                          aria-expanded={showAllSubs}
                          onClick={() => setShowAllSubs((value) => !value)}
                          className={`${rowClass} font-medium text-primary`}
                        >
                          {showAllSubs ? labels.seeLess : labels.seeAll}
                        </button>
                      </li>
                    ) : null}
                  </ul>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(body, document.body);
}
