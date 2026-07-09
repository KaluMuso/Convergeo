"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { createManageClient, type ListingSummary } from "../[id]/edit/_lib/manage-client";
import { Badge, Button, PriceBlock, Spinner } from "../new/_lib/ui";

type ListingsManageListProps = {
  locale: string;
};

function statusLabel(status: string, labels: Record<string, string>): string {
  return labels[status] ?? status;
}

export function ListingsManageList({ locale }: ListingsManageListProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adjustingId, setAdjustingId] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const manageClient = useMemo(() => createManageClient(getToken), [getToken]);

  const statusLabels = useMemo(
    () => ({
      draft: t("listings.manage.status.draft"),
      active: t("listings.manage.status.active"),
      paused: t("listings.manage.status.paused"),
    }),
    [t],
  );

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    manageClient
      .listListings()
      .then((rows) => {
        if (!cancelled) {
          setListings(rows);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(t("listings.manage.errors.loadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [manageClient, session, sessionLoading, t]);

  const handleStockAdjust = async (listingId: string, delta: number) => {
    setAdjustingId(listingId);
    try {
      const response = await manageClient.adjustStock(listingId, delta);
      setListings((current) =>
        current.map((listing) => (listing.id === listingId ? response.listing : listing)),
      );
    } catch {
      setError(t("listings.manage.errors.saveFailed"));
    } finally {
      setAdjustingId(null);
    }
  };

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-40 items-center justify-center">
        <Spinner label={t("listings.manage.loading")} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-text">{t("listings.manage.title")}</h1>
        <p className="text-sm text-text-2">{t("listings.manage.intro")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {listings.length === 0 ? (
        <div className="rounded-lg border border-border p-4 text-sm text-text-2">
          <p>{t("listings.manage.empty")}</p>
          <Link
            className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary"
            href={`/${locale}/listings/new`}
          >
            {t("listings.manage.createCta")}
          </Link>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {listings.map((listing) => (
            <li key={listing.id} className="rounded-lg border border-border p-3 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="truncate text-sm font-medium text-text">{listing.title}</p>
                  <PriceBlock ngwee={listing.price_ngwee} />
                </div>
                <Badge
                  variant={listing.status === "active" ? "free" : "sold_out"}
                  label={statusLabel(listing.status, statusLabels)}
                />
              </div>

              <div className="mt-3 flex items-center justify-between gap-3">
                <div className="text-xs text-text-2">
                  <span className="font-medium text-text">{t("listings.manage.stockLabel")}</span>
                  <span className="sr-only"> </span>
                  {listing.stock_mode === "always_available"
                    ? t("listings.manage.stockAlways")
                    : t("listings.manage.stockValue", { qty: listing.stock_qty ?? 0 })}
                </div>

                {listing.stock_mode === "tracked" ? (
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      className="min-h-11 min-w-11 px-3"
                      aria-label={t("listings.manage.decreaseStock")}
                      loadingLabel={t("listings.manage.loading")}
                      disabled={adjustingId === listing.id || (listing.stock_qty ?? 0) <= 0}
                      onClick={() => void handleStockAdjust(listing.id, -1)}
                    >
                      {t("listings.manage.decreaseSymbol")}
                    </Button>
                    <span className="min-w-8 text-center text-sm font-medium tabular-nums">
                      {listing.stock_qty ?? 0}
                    </span>
                    <Button
                      type="button"
                      variant="secondary"
                      className="min-h-11 min-w-11 px-3"
                      aria-label={t("listings.manage.increaseStock")}
                      loadingLabel={t("listings.manage.loading")}
                      disabled={adjustingId === listing.id}
                      onClick={() => void handleStockAdjust(listing.id, 1)}
                    >
                      {t("listings.manage.increaseSymbol")}
                    </Button>
                  </div>
                ) : null}
              </div>

              <Link
                className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
                href={`/${locale}/listings/${listing.id}/edit`}
              >
                {t("listings.manage.editCta")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
