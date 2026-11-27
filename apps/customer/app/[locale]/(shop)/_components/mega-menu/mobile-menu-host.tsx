"use client";

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import { OPEN_MOBILE_MENU_EVENT, preloadMobileDrawer } from "./menu-events";

import type { MegaMenuLabels } from "./labels";
import type { NavCategory } from "../category-tree";

// Drawer chunk (list rows, drill-down, session hook) loads on first open.
const MobileDrawer = lazy(() => import("./mobile-drawer"));

type MobileMenuHostProps = {
  locale: string;
  labels: MegaMenuLabels;
  loadCategories?: () => Promise<NavCategory[]>;
};

/**
 * Single drawer instance per page. Header menu buttons and the bottom-nav
 * "Browse" tab open it through `openMobileMenu()`; it restores focus to
 * whatever opened it.
 */
export function MobileMenuHost({ locale, labels, loadCategories }: MobileMenuHostProps) {
  const [open, setOpen] = useState(false);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const onOpen = () => {
      openerRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setOpen(true);
    };
    window.addEventListener(OPEN_MOBILE_MENU_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_MOBILE_MENU_EVENT, onOpen);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    openerRef.current?.focus();
  }, []);

  if (!open) {
    return null;
  }
  return (
    <Suspense fallback={null}>
      <MobileDrawer
        locale={locale}
        labels={labels}
        onClose={close}
        loadCategories={loadCategories}
      />
    </Suspense>
  );
}

type MobileMenuButtonProps = {
  label: string;
  className?: string;
  children: React.ReactNode;
  onOpen: () => void;
};

/** Hamburger trigger; preloads the drawer chunk on touch/hover/focus intent. */
export function MobileMenuButton({ label, className, children, onOpen }: MobileMenuButtonProps) {
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-label={label}
      onPointerDown={preloadMobileDrawer}
      onFocus={preloadMobileDrawer}
      onClick={onOpen}
      className={className}
    >
      {children}
    </button>
  );
}
