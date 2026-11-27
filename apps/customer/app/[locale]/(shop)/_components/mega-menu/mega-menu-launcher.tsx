"use client";

import { IconChevronDown } from "@vergeo/ui/src/icons";
import { lazy, Suspense, useCallback, useRef, useState } from "react";

import { preloadDesktopPanel } from "./menu-events";

import type { MegaMenuLabels } from "./labels";
import type { NavCategory } from "../category-tree";

// The panel (rail, tiles, data hook, focus trap) is its own chunk: it loads on
// first intent (hover / focus / click on the trigger), never with the header.
const MegaPanel = lazy(() => import("./mega-panel"));

type MegaMenuLauncherProps = {
  locale: string;
  labels: MegaMenuLabels;
  loadCategories?: () => Promise<NavCategory[]>;
  hoverDelayMs?: number;
};

/** Desktop (lg+) "All categories" button + lazily-loaded mega panel. */
export function MegaMenuLauncher({
  locale,
  labels,
  loadCategories,
  hoverDelayMs,
}: MegaMenuLauncherProps) {
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onPointerEnter={preloadDesktopPanel}
        onFocus={preloadDesktopPanel}
        onClick={() => {
          setEverOpened(true);
          setOpen((value) => !value);
        }}
        className="inline-flex min-h-11 items-center gap-1 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {labels.trigger}
        <IconChevronDown
          className={[
            "transition-transform duration-fast ease-std motion-reduce:transition-none",
            open ? "rotate-180" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        />
      </button>
      {everOpened && open ? (
        <Suspense fallback={null}>
          <MegaPanel
            locale={locale}
            labels={labels}
            onClose={close}
            loadCategories={loadCategories}
            hoverDelayMs={hoverDelayMs}
          />
        </Suspense>
      ) : null}
    </>
  );
}
