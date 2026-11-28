"use client";

import { glassClass } from "@vergeo/ui/src/glass";
import { useFocusTrap } from "@vergeo/ui/src/modal";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { createPortal } from "react-dom";

import {
  recordBrowsedCategory,
  readBrowsedCategories,
  type BrowsedCategory,
} from "./browsed-categories";
import { fillName, type MegaMenuLabels } from "./labels";
import { MenuTile } from "./menu-tile";
import { buildMenuModel, type MenuDept, type MenuLink } from "./nav-model";
import { useMenuTree } from "./use-menu-tree";

import type { NavCategory } from "../category-tree";

export const HOVER_INTENT_MS = 150;
const FOR_YOU_ID = "for-you";

export type MegaPanelProps = {
  locale: string;
  labels: MegaMenuLabels;
  onClose: () => void;
  /** Injectable for tests; defaults to the cached `GET /categories` loader. */
  loadCategories?: () => Promise<NavCategory[]>;
  hoverDelayMs?: number;
};

type RailEntry = {
  id: string;
  label: string;
  dept: MenuDept | null;
};

/**
 * Desktop "All categories" panel (Alibaba style): a rail of departments on the
 * left, the active department's sub-categories as round tiles on the right.
 * Hover (with a short intent delay so diagonal mouse moves do not flicker),
 * focus and click all switch the pane. Arrow keys walk the rail.
 */
export default function MegaPanel({
  locale,
  labels,
  onClose,
  loadCategories,
  hoverDelayMs = HOVER_INTENT_MS,
}: MegaPanelProps) {
  const pathname = usePathname();
  const firstPathRef = useRef(pathname);
  const panelRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const baseId = useId();
  const paneId = `${baseId}-pane`;

  const { tree, loading } = useMenuTree(true, labels.fallbackRoots, loadCategories);
  const [browsed, setBrowsed] = useState<BrowsedCategory[]>([]);
  const [top, setTop] = useState(0);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    setBrowsed(readBrowsedCategories());
    const header = document.querySelector('[data-testid="shop-header"]');
    setTop(header ? Math.round(header.getBoundingClientRect().bottom) : 0);
  }, []);

  // Close on route change (not on the initial mount).
  useEffect(() => {
    if (pathname !== firstPathRef.current) {
      onClose();
    }
  }, [pathname, onClose]);

  useFocusTrap(panelRef, true, onClose);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const model = useMemo(
    () => (tree ? buildMenuModel(tree, labels, locale) : null),
    [tree, labels, locale],
  );

  const entries = useMemo(() => {
    const list: Array<{ group: "foryou" | "products" | "services" | "events"; entry: RailEntry }> =
      [];
    if (browsed.length > 0) {
      list.push({ group: "foryou", entry: { id: FOR_YOU_ID, label: labels.forYou, dept: null } });
    }
    if (model) {
      for (const dept of model.products) {
        list.push({ group: "products", entry: { id: dept.id, label: dept.label, dept } });
      }
      list.push({
        group: "services",
        entry: { id: model.services.id, label: model.services.label, dept: model.services },
      });
      list.push({
        group: "events",
        entry: { id: model.events.id, label: model.events.label, dept: model.events },
      });
    }
    return list;
  }, [browsed, labels.forYou, model]);

  const resolvedActiveId =
    activeId && entries.some((item) => item.entry.id === activeId)
      ? activeId
      : (entries[0]?.entry.id ?? null);
  const active = entries.find((item) => item.entry.id === resolvedActiveId)?.entry ?? null;

  const cancelIntent = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const activateNow = useCallback(
    (id: string) => {
      cancelIntent();
      setActiveId(id);
    },
    [cancelIntent],
  );

  const onItemPointerEnter = (id: string) => (event: PointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === "touch") {
      return;
    }
    cancelIntent();
    if (id === resolvedActiveId) {
      return;
    }
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setActiveId(id);
    }, hoverDelayMs);
  };

  const railButtons = () =>
    Array.from(railRef.current?.querySelectorAll<HTMLButtonElement>("[data-rail-item]") ?? []);

  const onRailKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const buttons = railButtons();
    const index = buttons.findIndex((button) => button === document.activeElement);
    let next: HTMLButtonElement | undefined;
    switch (event.key) {
      case "ArrowDown":
        next = buttons[Math.min(buttons.length - 1, index + 1)];
        break;
      case "ArrowUp":
        next = buttons[Math.max(0, index - 1)];
        break;
      case "Home":
        next = buttons[0];
        break;
      case "End":
        next = buttons[buttons.length - 1];
        break;
      case "ArrowRight": {
        const first = paneRef.current?.querySelector<HTMLElement>("[data-menu-tile]");
        if (first) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      default:
        return;
    }
    event.preventDefault();
    next?.focus();
  };

  const onPaneKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      const current = railButtons().find((button) => button.dataset.railId === resolvedActiveId);
      current?.focus();
    }
  };

  const handleNavigate = (link: MenuLink) => () => {
    recordBrowsedCategory({ slug: link.slug, label: link.label, href: link.href });
    onClose();
  };

  const paneLinks: MenuLink[] = active
    ? active.dept
      ? active.dept.children
      : browsed.map((item) => ({
          id: item.href,
          slug: item.slug,
          label: item.label,
          href: item.href,
        }))
    : [];

  const groupLabel = {
    foryou: null,
    products: labels.groupProducts,
    services: labels.groupServices,
    events: labels.groupEvents,
  } as const;

  const body = (
    <div data-testid="mega-panel-root">
      <div
        data-testid="mega-panel-scrim"
        aria-hidden="true"
        onClick={onClose}
        style={{
          top,
          backgroundColor: "color-mix(in srgb, var(--panel) 45%, transparent)",
        }}
        className="fixed inset-x-0 bottom-0 z-[60]"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-label={labels.panelAria}
        tabIndex={-1}
        style={{ top: top + 4 }}
        className={`${glassClass("overlay")} motion-fade fixed left-1/2 z-[61] flex max-h-[min(36rem,calc(100vh-6rem))] w-[min(66rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg`}
      >
        <div
          ref={railRef}
          onKeyDown={onRailKeyDown}
          aria-label={labels.railAria}
          role="group"
          className="w-56 shrink-0 overflow-y-auto border-r border-border py-2"
        >
          {model === null ? (
            <p className="px-4 py-3 text-sm text-text-2">{labels.loading}</p>
          ) : (
            entries.map((item, index) => {
              const showHeading = index === 0 || entries[index - 1]?.group !== item.group;
              const heading = groupLabel[item.group];
              const isActive = item.entry.id === resolvedActiveId;
              return (
                <div key={item.entry.id}>
                  {showHeading && heading ? (
                    <p className="px-4 pb-1 pt-3 text-micro font-semibold uppercase tracking-wide text-text-3">
                      {heading}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    data-rail-item
                    data-rail-id={item.entry.id}
                    aria-controls={paneId}
                    aria-current={isActive ? "true" : undefined}
                    tabIndex={isActive ? 0 : -1}
                    onPointerEnter={onItemPointerEnter(item.entry.id)}
                    onPointerLeave={cancelIntent}
                    onFocus={() => activateNow(item.entry.id)}
                    onClick={() => activateNow(item.entry.id)}
                    className={`flex min-h-11 w-full items-center justify-between gap-2 px-4 text-left text-sm transition-colors focus-visible:outline-none focus-visible:shadow-focusRing ${
                      isActive
                        ? "bg-bg-2 font-semibold text-primary"
                        : "text-text-2 hover:bg-bg-2 hover:text-text"
                    }`}
                  >
                    <span className="min-w-0 truncate">{item.entry.label}</span>
                  </button>
                </div>
              );
            })
          )}
        </div>

        <div
          ref={paneRef}
          id={paneId}
          role="region"
          aria-label={active?.label ?? labels.panelAria}
          onKeyDown={onPaneKeyDown}
          className="min-w-0 flex-1 overflow-y-auto p-5"
        >
          {loading || model === null ? (
            <p className="text-sm text-text-2">{labels.loading}</p>
          ) : active === null ? (
            <p className="text-sm text-text-2">{labels.empty}</p>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h2 className="font-display text-h3 font-bold text-display-ink">{active.label}</h2>
                <Link
                  href={`/${locale}/search`}
                  onClick={onClose}
                  className="inline-flex min-h-11 items-center rounded-sm text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {labels.browseFeatured}
                </Link>
              </div>
              <ul className="m-0 grid list-none grid-cols-3 gap-3 p-0 xl:grid-cols-5 lg:grid-cols-4">
                {active.dept ? (
                  <li>
                    <MenuTile
                      kind="all"
                      href={active.dept.href}
                      label={labels.viewAll}
                      ariaLabel={fillName(labels.viewAllIn, active.label)}
                      onNavigate={handleNavigate(active.dept)}
                    />
                  </li>
                ) : null}
                {paneLinks.map((link) => (
                  <li key={link.id}>
                    <MenuTile
                      href={link.href}
                      label={link.label}
                      seed={link.slug}
                      onNavigate={handleNavigate(link)}
                    />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(body, document.body);
}
