"use client";

import { useSession } from "@vergeo/auth/use-session";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { VendorRouteHeader } from "../../_components/vendor-route-header";
import { ListSkeleton } from "../../_components/vendor-skeletons";
import { vendorErrorMessageKey } from "../../_lib/vendor-errors";
import { createManageClient, type ListingSummary } from "../[id]/edit/_lib/manage-client";
import { Badge, PriceBlock } from "../new/_lib/ui";

import { ListingStatusGuide, ListingTipsPanel, ListingVisibilityHint } from "./listing-guide";
import { ListingProductStatusChip } from "./listing-product-status";
import { PlanUsageCard } from "./plan-usage-card";

type ListingsManageListProps = {
  locale: string;
};

function statusLabel(status: string, labels: Record<string, string>): string {
  return labels[status] ?? status;
}

function statusVariant(status: string): "free" | "sold_out" | "new" {
  if (status === "active") return "free";
  if (status === "paused") return "sold_out";
  return "new";
}

export function ListingsManageList({ locale }: ListingsManageListProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const { session, loading: sessionLoading } = useSession();
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

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

  const loadListings = useCallback(async () => {
    if (!session) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setErrorKey(null);
    try {
      const rows = await manageClient.listListings();
      setListings(rows);
    } catch (caught) {
      setListings([]);
      setErrorKey(vendorErrorMessageKey(caught, "listingsManage"));
    } finally {
      setLoading(false);
    }
  }, [manageClient, session]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadListings();
  }, [loadListings, reloadKey, session, sessionLoading]);

  if (sessionLoading || loading) {
    return <ListSkeleton label={t("listings.manage.loading")} />;
  }

  if (!session) {
    return (
      <VendorErrorState
        title={t("listings.errors.authRequired")}
        retryLabel={tCommon("common.retry")}
      />
    );
  }

  if (errorKey) {
    return (
      <VendorErrorState
        title={t(errorKey as "listings.manage.errors.loadFailed")}
        body={t("listings.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => setReloadKey((value) => value + 1)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <VendorRouteHeader
        title={t("listings.manage.title")}
        subtitle={t("listings.manage.intro")}
        actions={
          <Link
            className="press-scale inline-flex min-h-11 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)]"
            href={`/${locale}/listings/new`}
          >
            {t("listings.manage.createCta")}
          </Link>
        }
      />

      <div className="px-1">
        <PlanUsageCard locale={locale} refreshKey={listings.length} />
      </div>

      <div className="px-1">
        <Link
          className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-semibold text-surface"
          href={`/${locale}/listings/new`}
        >
          {t("listings.manage.createCta")}
        </Link>
      </div>

      {listings.length === 0 ? (
        <div className="flex flex-col gap-3 px-1">
          <VendorEmptyState
            illustration="no-products"
            title={t("listings.manage.emptyTitle")}
            body={t("listings.manage.empty")}
          />
          <ListingTipsPanel defaultOpen />
        </div>
      ) : (
        <>
          <div className="px-1">
            <ListingStatusGuide />
          </div>
          <div className="grid grid-cols-1 gap-4 px-1 md:grid-cols-2 2xl:grid-cols-3">
            {listings.map((listing) => {
              const coverImage = [...(listing.images ?? [])].sort(
                (left, right) => left.position - right.position,
              )[0];
              return (
                <div
                  key={listing.id}
                  className="flex min-w-0 flex-col rounded-lg border border-border p-4 shadow-sm lg:p-5"
                >
                  <div className="flex items-start gap-3">
                    {coverImage ? (
                      <CloudinaryImage
                        publicId={coverImage.cloudinary_public_id}
                        alt={listing.title}
                        width={64}
                        ratio={1}
                        className="size-16 shrink-0 rounded-lg border border-border object-cover"
                      />
                    ) : (
                      <div className="flex size-16 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border bg-bg-2 p-1 text-center">
                        <Link
                          className="text-[0.65rem] font-medium leading-tight text-primary underline-offset-2 hover:underline"
                          href={`/${locale}/listings/${listing.id}/edit#photos`}
                        >
                          {t("listings.manage.addPhotoLink")}
                        </Link>
                      </div>
                    )}
                    <div className="min-w-0 flex-1 space-y-1">
                      <p className="line-clamp-2 break-words text-sm font-medium text-text">
                        {listing.title}
                      </p>
                      <PriceBlock ngwee={listing.price_ngwee} />
                    </div>
                  </div>

                  {/* Status lives on its own full-width row so the hint never wraps in a
                      narrow column beside the thumbnail (360px phones). */}
                  <div
                    className="mt-3 flex flex-col gap-2 border-t border-border pt-3"
                    data-testid="listing-status-row"
                  >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="sr-only">{t("listings.manage.statusLabel")}</span>
                      <Badge
                        variant={statusVariant(listing.status)}
                        label={statusLabel(listing.status, statusLabels)}
                      />
                      <ListingProductStatusChip
                        listingStatus={listing.status}
                        productStatus={listing.product_status}
                      />
                    </div>
                    <ListingVisibilityHint status={listing.status} />
                  </div>

                  <div className="mt-3 flex items-center justify-between gap-3">
                    <div className="text-xs text-text-2">
                      <span className="font-medium text-text">
                        {t("listings.manage.stockLabel")}
                      </span>
                      <span className="sr-only"> </span>
                      {listing.stock_mode === "always_available"
                        ? t("listings.manage.stockAlways")
                        : t("listings.manage.stockValue", { qty: listing.stock_qty ?? 0 })}
                    </div>

                    {listing.stock_mode === "tracked" ? (
                      <Link
                        className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
                        href={`/${locale}/listings/${listing.id}/edit#stock`}
                      >
                        {t("listings.manage.stock.heading")}
                      </Link>
                    ) : null}
                  </div>

                  <Link
                    className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
                    href={`/${locale}/listings/${listing.id}/edit`}
                  >
                    {t("listings.manage.editCta")}
                  </Link>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
