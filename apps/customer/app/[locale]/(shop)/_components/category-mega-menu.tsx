"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { IconChevronDown } from "@vergeo/ui/src/icons";
import { useFocusTrap } from "@vergeo/ui/src/modal";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { buildCategoryTree, type CategoryRecord, type NavCategory } from "./category-tree";

export type { NavCategory } from "./category-tree";
export { buildCategoryTree } from "./category-tree";

export type CategoryMegaMenuLabels = {
  trigger: string;
  panelAria: string;
  loading: string;
  viewAll: string;
  empty?: string;
};

type CategoryMegaMenuProps = {
  locale: string;
  labels: CategoryMegaMenuLabels;
  /** Injectable for tests; defaults to a public (anon) browser-client query. */
  loadCategories?: () => Promise<NavCategory[]>;
  /** Close the panel when the document scrolls (desktop sticky header). */
  closeOnScroll?: boolean;
};

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
 * Focus is trapped while open. The category tree loads lazily on first open.
 */
export function CategoryMegaMenu({
  locale,
  labels,
  loadCategories = defaultLoadCategories,
  closeOnScroll = false,
}: CategoryMegaMenuProps) {
  const [open, setOpen] = useState(false);
  const [categories, setCategories] = useState<NavCategory[] | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const startedRef = useRef(false);
  const mountedRef = useRef(true);
  const loadRef = useRef(loadCategories);
  const panelId = useId();

  useFocusTrap(panelRef, open, () => {
    setOpen(false);
    triggerRef.current?.focus();
  });

  useEffect(() => {
    loadRef.current = loadCategories;
  }, [loadCategories]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

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
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !closeOnScroll) {
      return;
    }
    const onScroll = () => {
      setOpen(false);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [open, closeOnScroll]);

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
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
      <div
        ref={panelRef}
        id={panelId}
        role="dialog"
        aria-label={labels.panelAria}
        hidden={!open}
        tabIndex={-1}
        className="absolute left-0 top-full z-50 mt-1 max-h-[70vh] w-[min(44rem,90vw)] overflow-auto rounded-lg border border-border bg-surface p-4 shadow-3 motion-fade"
      >
        {loading || categories === null ? (
          <p className="text-sm text-text-2">{labels.loading}</p>
        ) : categories.length === 0 ? (
          <p className="text-sm text-text-2">{labels.empty ?? labels.loading}</p>
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
