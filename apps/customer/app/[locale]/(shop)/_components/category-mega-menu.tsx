"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

export type NavCategory = {
  id: string;
  name: string;
  slug: string;
  children: Array<{ id: string; name: string; slug: string }>;
};

type CategoryRecord = {
  id: string;
  name: string;
  slug: string;
  position: number;
  parent_id: string | null;
  prohibited: boolean;
};

export type CategoryMegaMenuLabels = {
  trigger: string;
  panelAria: string;
  loading: string;
  viewAll: string;
};

type CategoryMegaMenuProps = {
  locale: string;
  labels: CategoryMegaMenuLabels;
  /** Injectable for tests; defaults to a public (anon) browser-client query. */
  loadCategories?: () => Promise<NavCategory[]>;
};

function byPosition(left: { position: number }, right: { position: number }): number {
  return left.position - right.position;
}

/** Group a flat category list into top-level entries with their children. */
export function buildCategoryTree(rows: CategoryRecord[]): NavCategory[] {
  const usable = rows.filter((row) => !row.prohibited);
  return usable
    .filter((row) => row.parent_id === null)
    .sort(byPosition)
    .map((top) => ({
      id: top.id,
      name: top.name,
      slug: top.slug,
      children: usable
        .filter((row) => row.parent_id === top.id)
        .sort(byPosition)
        .map((child) => ({ id: child.id, name: child.name, slug: child.slug })),
    }));
}

async function defaultLoadCategories(): Promise<NavCategory[]> {
  // Category tree is publicly readable (RLS: categories_public_select "using (true)"),
  // so the anon browser client can fetch it lazily without a server round-trip in the
  // shop layout — which would otherwise force every shop route to render dynamically.
  // getBrowserClient loads @supabase/ssr dynamically (only when the menu first
  // opens) so it does not sit in the shared shop-shell first-load bundle.
  const supabase = await getBrowserClient();
  const { data, error } = await supabase
    .from("categories")
    .select("id, name, slug, position, parent_id, prohibited")
    .eq("prohibited", false)
    .order("position", { ascending: true });
  if (error || !data) {
    return [];
  }
  return buildCategoryTree(data as CategoryRecord[]);
}

/**
 * Desktop "All Categories" disclosure menu. Accessible by design: a real
 * button toggles a panel of real links (no hover-only trap), so it behaves
 * identically for mouse, touch, and keyboard — click/Enter/Space toggles, and
 * Escape or an outside click closes it and restores focus to the trigger.
 * (Hover-to-open is deliberately avoided: on touch devices a synthetic
 * mouseenter would fire before the tap's click and toggle the panel shut.)
 * The category tree loads lazily the first time the menu opens.
 */
export function CategoryMegaMenu({
  locale,
  labels,
  loadCategories = defaultLoadCategories,
}: CategoryMegaMenuProps) {
  const [open, setOpen] = useState(false);
  const [categories, setCategories] = useState<NavCategory[] | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const startedRef = useRef(false);
  const mountedRef = useRef(true);
  const loadRef = useRef(loadCategories);
  const panelId = useId();

  useEffect(() => {
    loadRef.current = loadCategories;
  }, [loadCategories]);

  useEffect(() => {
    // Reset on (re)mount — React StrictMode runs mount→cleanup→mount in dev, and
    // without restoring this the load guards below would stay false for the
    // component's whole life, wedging the panel on "Loading…".
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Lazy-load the tree once, the first time the menu opens. Guarded by a ref
  // (not by state in the dep array) so the setLoading re-render can't re-enter
  // and cancel the in-flight fetch.
  useEffect(() => {
    if (!open || startedRef.current) {
      return;
    }
    startedRef.current = true;
    setLoading(true);
    loadRef
      .current()
      .then((tree) => {
        if (mountedRef.current) {
          setCategories(tree);
        }
      })
      .catch(() => {
        if (mountedRef.current) {
          setCategories([]);
        }
      })
      .finally(() => {
        if (mountedRef.current) {
          setLoading(false);
        }
      });
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-11 items-center gap-1 rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {labels.trigger}
        <span aria-hidden className="text-[0.6rem] leading-none">
          {"▾"}
        </span>
      </button>
      <div
        id={panelId}
        aria-label={labels.panelAria}
        hidden={!open}
        className="absolute left-0 top-full z-50 mt-1 max-h-[70vh] w-[min(44rem,90vw)] overflow-auto rounded-lg border border-border bg-surface p-4 shadow-3"
      >
        {loading || categories === null ? (
          <p className="text-sm text-text-2">{labels.loading}</p>
        ) : (
          <div className="space-y-4">
            <ul className="grid list-none grid-cols-2 gap-x-6 gap-y-4 p-0 sm:grid-cols-3">
              {categories.map((category) => (
                <li key={category.id} className="min-w-0">
                  <Link
                    href={`/${locale}/c/${category.slug}`}
                    onClick={() => setOpen(false)}
                    className="block truncate font-display text-h3 text-display-ink transition-colors hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
                  >
                    {category.name}
                  </Link>
                  {category.children.length > 0 ? (
                    <ul className="mt-1.5 list-none space-y-1 p-0">
                      {category.children.map((child) => (
                        <li key={child.id} className="min-w-0">
                          <Link
                            href={`/${locale}/c/${child.slug}`}
                            onClick={() => setOpen(false)}
                            className="block truncate text-sm text-text-2 transition-colors hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
                          >
                            {child.name}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
            <Link
              href={`/${locale}/categories`}
              onClick={() => setOpen(false)}
              className="inline-flex min-h-11 items-center text-sm font-medium text-primary transition-colors hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {labels.viewAll}
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
