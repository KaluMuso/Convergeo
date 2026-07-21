"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { IconChevronDown } from "@vergeo/ui/src/icons";
import { useFocusTrap } from "@vergeo/ui/src/modal";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

import { buildCategoryTree, type CategoryRecord, type NavCategory } from "./category-tree";
import {
  fetchMegaMenuMerchSlot,
  readMerchPreviewToken,
  withLocaleHref,
  type MegaMenuMerchPayload,
} from "./mega-menu-merch";
import { useMerchPreviewToken, withMerchPreviewParam } from "./merch-preview-nav";

export type { NavCategory } from "./category-tree";
export { buildCategoryTree } from "./category-tree";

export type FeaturedMini = {
  title: string;
  href: string;
  priceLabel: string;
};

export type CategoryMegaMenuLabels = {
  trigger: string;
  panelAria: string;
  loading: string;
  viewAll: string;
  empty?: string;
  featuredTitle: string;
  featuredPromo: string;
  featuredPromoCta: string;
};

type MegaMenuFeaturedContent = {
  minis: FeaturedMini[];
  promoText: string;
  promoCtaLabel: string;
  promoHref: string;
};

type CategoryMegaMenuProps = {
  locale: string;
  labels: CategoryMegaMenuLabels;
  /** Injectable for tests; defaults to a public (anon) browser-client query. */
  loadCategories?: () => Promise<NavCategory[]>;
  /** Injectable featured sidebar; defaults to CMS slot with catalog fallback. */
  loadFeaturedContent?: (locale: string) => Promise<MegaMenuFeaturedContent>;
  /** Close the panel when the document scrolls (desktop sticky header). */
  closeOnScroll?: boolean;
};

async function defaultLoadCategories(): Promise<NavCategory[]> {
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

type CatalogListingItem = {
  title: string;
  product_slug: string | null;
  price_ngwee: number;
};

async function loadCatalogFeaturedMinis(locale: string): Promise<FeaturedMini[]> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return [];
  }
  try {
    const client = createApiClient({ baseUrl });
    const response = await client.request<{ items: CatalogListingItem[] }>(
      "/catalog/listings?sort=newest&limit=3",
    );
    return response.items
      .filter((item) => item.product_slug)
      .map((item) => ({
        title: item.title,
        href: `/${locale}/p/${item.product_slug}`,
        priceLabel: formatK(item.price_ngwee),
      }));
  } catch {
    return [];
  }
}

function featuredFromMerch(locale: string, merch: MegaMenuMerchPayload): FeaturedMini[] {
  return merch.featuredMinis.map((mini) => ({
    title: mini.title,
    href: withLocaleHref(locale, mini.href),
    priceLabel: mini.priceLabel ?? "",
  }));
}

async function defaultLoadFeaturedContent(
  locale: string,
  labels: CategoryMegaMenuLabels,
): Promise<MegaMenuFeaturedContent> {
  const previewToken = readMerchPreviewToken();
  const merch = await fetchMegaMenuMerchSlot(previewToken);

  const cmsMinis = merch ? featuredFromMerch(locale, merch) : [];
  const minis = cmsMinis.length > 0 ? cmsMinis : await loadCatalogFeaturedMinis(locale);

  return {
    minis,
    promoText: merch?.promoText ?? labels.featuredPromo,
    promoCtaLabel: merch?.promoCtaLabel ?? labels.featuredPromoCta,
    promoHref: withLocaleHref(locale, merch?.promoHref ?? `/${locale}/search`),
  };
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
  loadFeaturedContent,
  closeOnScroll = false,
}: CategoryMegaMenuProps) {
  const previewToken = useMerchPreviewToken();
  const previewHref = useCallback(
    (href: string) => withMerchPreviewParam(href, previewToken),
    [previewToken],
  );
  const resolveFeaturedContent = useCallback(
    (activeLocale: string) =>
      loadFeaturedContent
        ? loadFeaturedContent(activeLocale)
        : defaultLoadFeaturedContent(activeLocale, labels),
    [labels, loadFeaturedContent],
  );

  const [open, setOpen] = useState(false);
  const [categories, setCategories] = useState<NavCategory[] | null>(null);
  const [featuredContent, setFeaturedContent] = useState<MegaMenuFeaturedContent | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const startedRef = useRef(false);
  const mountedRef = useRef(true);
  const loadRef = useRef(loadCategories);
  const featuredRef = useRef(resolveFeaturedContent);
  const panelId = useId();

  const closeMenu = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  useFocusTrap(panelRef, open, closeMenu);

  useEffect(() => {
    loadRef.current = loadCategories;
  }, [loadCategories]);

  useEffect(() => {
    featuredRef.current = resolveFeaturedContent;
  }, [resolveFeaturedContent]);

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
    void Promise.all([loadRef.current(), featuredRef.current(locale)])
      .then(([tree, featured]) => {
        if (mountedRef.current) {
          setCategories(tree);
          setFeaturedContent(featured);
        }
      })
      .catch(() => {
        if (mountedRef.current) {
          setCategories([]);
          setFeaturedContent({
            minis: [],
            promoText: labels.featuredPromo,
            promoCtaLabel: labels.featuredPromoCta,
            promoHref: `/${locale}/search`,
          });
        }
      })
      .finally(() => {
        if (mountedRef.current) {
          setLoading(false);
        }
      });
  }, [labels.featuredPromo, labels.featuredPromoCta, locale, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        closeMenu();
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, closeMenu]);

  useEffect(() => {
    if (!open || !closeOnScroll) {
      return;
    }
    const onScroll = () => {
      closeMenu();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [open, closeOnScroll, closeMenu]);

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
        className="absolute left-0 top-full z-50 mt-1 max-h-[70vh] w-[min(52rem,92vw)] overflow-auto rounded-lg border border-border bg-surface p-4 shadow-3 motion-fade"
      >
        {loading || categories === null || featuredContent === null ? (
          <p className="text-sm text-text-2">{labels.loading}</p>
        ) : categories.length === 0 ? (
          <p className="text-sm text-text-2">{labels.empty ?? labels.loading}</p>
        ) : (
          <div className="flex flex-col gap-4 lg:flex-row lg:gap-6">
            <div className="min-w-0 flex-1 space-y-4">
              <ul className="grid list-none grid-cols-2 gap-x-6 gap-y-4 p-0 sm:grid-cols-3">
                {categories.map((category) => (
                  <li key={category.id} className="min-w-0">
                    <Link
                      href={previewHref(`/${locale}/c/${category.slug}`)}
                      onClick={closeMenu}
                      className="block truncate font-display text-h3 text-display-ink transition-colors hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
                    >
                      {category.name}
                    </Link>
                    {category.children.length > 0 ? (
                      <ul className="mt-1.5 list-none space-y-1 p-0">
                        {category.children.map((child) => (
                          <li key={child.id} className="min-w-0">
                            <Link
                              href={previewHref(`/${locale}/c/${child.slug}`)}
                              onClick={closeMenu}
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
                href={previewHref(`/${locale}/categories`)}
                onClick={closeMenu}
                className="inline-flex min-h-11 items-center text-sm font-medium text-primary transition-colors hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {labels.viewAll}
              </Link>
            </div>

            <aside
              aria-labelledby="mega-menu-featured-title"
              className="w-full shrink-0 rounded-lg border border-border bg-bg-2 p-3 lg:w-56"
              data-testid="mega-menu-featured"
            >
              <h3 id="mega-menu-featured-title" className="mb-2 text-sm font-semibold text-text">
                {labels.featuredTitle}
              </h3>
              {featuredContent.minis.length > 0 ? (
                <ul className="m-0 list-none space-y-2 p-0">
                  {featuredContent.minis.map((mini) => (
                    <li key={mini.href}>
                      <Link
                        href={previewHref(mini.href)}
                        onClick={closeMenu}
                        className="block rounded-md px-2 py-1.5 transition-colors hover:bg-surface focus-visible:outline-none focus-visible:shadow-focusRing"
                      >
                        <span className="block truncate text-sm font-medium text-text">
                          {mini.title}
                        </span>
                        {mini.priceLabel ? (
                          <span className="text-xs text-text-2">{mini.priceLabel}</span>
                        ) : null}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="mt-3 text-xs text-text-2">{featuredContent.promoText}</p>
              <Link
                href={previewHref(featuredContent.promoHref)}
                onClick={closeMenu}
                className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {featuredContent.promoCtaLabel}
              </Link>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
