"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { addCartItem } from "../../_components/cart/mini-cart-drawer";
import { useLocalWishlistSlugs } from "../../_components/plp/use-local-wishlist";

import type { ProductDetail } from "../../_components/pdp/fetch-product";

export type SavedItemsLabels = {
  title: string;
  description: string;
  disclaimer: string;
  emptyTitle: string;
  emptyBody: string;
  browseCta: string;
  loading: string;
  loadError: string;
  remove: string;
  removeLabel: string;
  moveToCart: string;
  movingToCart: string;
  viewProduct: string;
  unavailable: string;
  outOfStock: string;
  fromPrice: string;
  signedOutNote: string;
};

type Props = {
  locale: string;
  labels: SavedItemsLabels;
  signedIn: boolean;
};

type RowState =
  | { kind: "loading"; slug: string }
  | { kind: "product"; slug: string; product: ProductDetail }
  | { kind: "unavailable"; slug: string }
  | { kind: "error"; slug: string };

async function loadProduct(slug: string): Promise<RowState> {
  try {
    const base = getApiBaseUrl();
    const response = await fetch(`${base}/products/${encodeURIComponent(slug)}`, {
      credentials: "omit",
    });
    if (response.status === 404) {
      return { kind: "unavailable", slug };
    }
    if (!response.ok) {
      return { kind: "error", slug };
    }
    const product = (await response.json()) as ProductDetail;
    return { kind: "product", slug, product };
  } catch {
    return { kind: "error", slug };
  }
}

function lowestInStockListing(product: ProductDetail) {
  const inStock = product.listings.filter((listing) => listing.in_stock);
  const pool = inStock.length > 0 ? inStock : product.listings;
  if (pool.length === 0) {
    return null;
  }
  return pool.reduce((best, listing) => (listing.price_ngwee < best.price_ngwee ? listing : best));
}

export function SavedItemsPanel({ locale, labels, signedIn }: Props) {
  const { slugs, hydrated, remove } = useLocalWishlistSlugs();
  const [rows, setRows] = useState<RowState[]>([]);
  const [cartBusy, setCartBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (slugs.length === 0) {
      setRows([]);
      return;
    }
    let cancelled = false;
    setRows(slugs.map((slug) => ({ kind: "loading", slug })));
    void Promise.all(slugs.map((slug) => loadProduct(slug))).then((next) => {
      if (!cancelled) {
        setRows(next);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [hydrated, slugs]);

  const amountLocale = `${locale}-ZM`;

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-display text-h1 text-display-ink">{labels.title}</h1>
        <p className="text-sm text-text-2">{labels.description}</p>
        <p className="text-xs text-text-3" data-testid="saved-items-disclaimer">
          {labels.disclaimer}
        </p>
        {!signedIn ? (
          <p className="text-xs text-text-2" data-testid="saved-items-signed-out-note">
            {labels.signedOutNote}
          </p>
        ) : null}
      </header>

      {actionError ? (
        <p role="alert" className="text-sm text-danger">
          {actionError}
        </p>
      ) : null}

      {!hydrated ? (
        <div className="space-y-3" data-testid="saved-items-loading" aria-busy="true">
          <p className="sr-only">{labels.loading}</p>
          <Skeleton height="4rem" />
          <Skeleton height="4rem" />
        </div>
      ) : null}

      {hydrated && slugs.length === 0 ? (
        <EmptyState
          title={labels.emptyTitle}
          body={labels.emptyBody}
          data-testid="saved-items-empty"
          action={
            <LinkButton
              href={`/${locale}`}
              variant="primary"
              className="text-sm"
              LinkComponent={Link}
            >
              {labels.browseCta}
            </LinkButton>
          }
        />
      ) : null}

      {hydrated && slugs.length > 0 ? (
        <ul className="space-y-3" data-testid="saved-items-list">
          {rows.map((row) => {
            if (row.kind === "loading") {
              return (
                <li key={row.slug}>
                  <Skeleton height="5rem" />
                </li>
              );
            }

            if (row.kind === "unavailable" || row.kind === "error") {
              return (
                <li
                  key={row.slug}
                  className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
                  data-testid={`saved-item-unavailable-${row.slug}`}
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm text-text-2">{row.slug}</p>
                    <p className="text-sm text-text-2" role="status">
                      {row.kind === "unavailable" ? labels.unavailable : labels.loadError}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded border border-border px-3 text-sm font-medium text-text"
                    onClick={() => remove(row.slug)}
                    aria-label={labels.removeLabel.replace("{name}", row.slug)}
                  >
                    {labels.remove}
                  </button>
                </li>
              );
            }

            const listing = lowestInStockListing(row.product);
            const inStock = Boolean(listing?.in_stock);
            const busy = cartBusy === row.slug;

            return (
              <li
                key={row.slug}
                className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
                data-testid={`saved-item-${row.slug}`}
              >
                <div className="min-w-0 space-y-1">
                  <Link
                    href={`/${locale}/p/${row.slug}`}
                    className="font-medium text-display-ink underline-offset-2 hover:underline"
                  >
                    {row.product.name}
                  </Link>
                  {listing ? (
                    <p className="font-mono text-sm text-text">
                      {labels.fromPrice.replace(
                        "{price}",
                        formatK(listing.price_ngwee, { locale: amountLocale }),
                      )}
                    </p>
                  ) : (
                    <p className="text-sm text-text-2">{labels.unavailable}</p>
                  )}
                  {!inStock && listing ? (
                    <p className="text-sm text-warning" role="status">
                      {labels.outOfStock}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <LinkButton
                    href={`/${locale}/p/${row.slug}`}
                    variant="secondary"
                    className="px-3 text-sm"
                    LinkComponent={Link}
                  >
                    {labels.viewProduct}
                  </LinkButton>
                  {listing && inStock ? (
                    <Button
                      type="button"
                      variant="primary"
                      size="md"
                      loading={busy}
                      loadingLabel={labels.movingToCart}
                      disabled={busy}
                      onClick={() => {
                        setActionError(null);
                        setCartBusy(row.slug);
                        void addCartItem(listing.id, 1)
                          .then(() => {
                            window.location.href = `/${locale}/cart`;
                          })
                          .catch(() => {
                            setActionError(labels.loadError);
                          })
                          .finally(() => {
                            setCartBusy(null);
                          });
                      }}
                    >
                      {labels.moveToCart}
                    </Button>
                  ) : null}
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded border border-border px-3 text-sm font-medium text-text"
                    onClick={() => remove(row.slug)}
                    aria-label={labels.removeLabel.replace("{name}", row.product.name)}
                  >
                    {labels.remove}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
