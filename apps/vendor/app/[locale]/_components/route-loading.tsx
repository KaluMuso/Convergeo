import { getTranslations } from "next-intl/server";

import { VendorPageSkeleton } from "./page-skeleton";
import { VendorPage } from "./vendor-page";
import {
  AnalyticsSkeleton,
  DashboardSkeleton,
  ListSkeleton,
  OrderDetailSkeleton,
} from "./vendor-skeletons";

export type RouteLoadingVariant = "page" | "list" | "dashboard" | "analytics" | "order";

async function loadingLabel(): Promise<string> {
  try {
    const t = await getTranslations("common");
    return t("common.loading");
  } catch {
    // Never let a missing request locale turn a loading shell into an error page.
    return "";
  }
}

/**
 * Instant route-level fallback shown by `loading.tsx` while a segment streams in. The
 * shapes match the client views that replace them (same cards, same spacing), so the
 * page does not jump when data lands on a slow connection.
 */
export async function RouteLoading({ variant = "page" }: { variant?: RouteLoadingVariant }) {
  const label = await loadingLabel();
  return (
    <VendorPage width="full">
      {variant === "list" ? <ListSkeleton label={label} rows={4} /> : null}
      {variant === "dashboard" ? <DashboardSkeleton label={label} /> : null}
      {variant === "analytics" ? <AnalyticsSkeleton label={label} /> : null}
      {variant === "order" ? <OrderDetailSkeleton label={label} /> : null}
      {variant === "page" ? <VendorPageSkeleton label={label} /> : null}
    </VendorPage>
  );
}

/** `loading.tsx` factory: `export default routeLoading("list")`. */
export function routeLoading(variant: RouteLoadingVariant) {
  return async function Loading() {
    return <RouteLoading variant={variant} />;
  };
}
