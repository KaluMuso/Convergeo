"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import {
  LcClipboardList,
  LcLayoutGrid,
  LcShoppingBag,
  LcTrendingUp,
} from "@vergeo/ui/src/lucide-icons";
import { StatCard } from "@vergeo/ui/src/stat-card";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { HomeTaskList } from "../../_components/home-tasks";
import { VendorGrid } from "../../_components/vendor-page";
import { VendorQuickActionGrid } from "../../_components/vendor-quick-action-grid";
import { VendorRouteHeader } from "../../_components/vendor-route-header";
import { VendorShopStatusCard } from "../../_components/vendor-shop-status";
import { DashboardSkeleton } from "../../_components/vendor-skeletons";
import { buildHomeTasks } from "../../_lib/home-tasks";
import { isAuditableApproved } from "../../_lib/kyc-integrity";
import { vendorErrorMessageKey } from "../../_lib/vendor-errors";
import {
  createAnalyticsClient,
  type VendorAnalyticsSummary,
} from "../../analytics/_lib/analytics-client";
import { createManageClient } from "../../listings/[id]/edit/_lib/manage-client";
import { buildKycChecklist } from "../../onboarding/_lib/kyc-checklist";
import { createKycClient } from "../../onboarding/_lib/kyc-client";
import { createPayoutsClient } from "../../payouts/_lib/payouts-client";
import { isBoundByDispatchCutoff } from "../_lib/order-guidance";

import { OrderCard } from "./order-card";
import { useDispatchCutoff } from "./order-guidance";
import {
  createOrdersQueueClient,
  readQueueCache,
  writeQueueCache,
  type VendorDashboard,
} from "./orders-queue-client";

import type { KycApplication } from "../../onboarding/_lib/types";

type VendorHomeViewProps = {
  locale: string;
};

export function VendorHomeView({ locale }: VendorHomeViewProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const { session, loading: sessionLoading } = useSession();
  const [dashboard, setDashboard] = useState<VendorDashboard | null>(null);
  const [analyticsSummary, setAnalyticsSummary] = useState<VendorAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [kycApp, setKycApp] = useState<KycApplication | null>(null);
  const [payoutMissing, setPayoutMissing] = useState<boolean | null>(null);
  const [productsInReviewCount, setProductsInReviewCount] = useState(0);
  const cutoff = useDispatchCutoff();

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const queueClient = useMemo(() => createOrdersQueueClient(getToken), [getToken]);
  const kycClient = useMemo(() => createKycClient(getToken), [getToken]);
  const analyticsClient = useMemo(() => createAnalyticsClient(getToken), [getToken]);
  const payoutsClient = useMemo(() => createPayoutsClient(getToken), [getToken]);
  const manageClient = useMemo(() => createManageClient(getToken), [getToken]);

  const load = useCallback(async () => {
    if (!session) {
      return;
    }
    setLoading(true);
    setErrorKey(null);
    try {
      const [data, kyc, summary] = await Promise.all([
        queueClient.getDashboard(),
        kycClient.getApplication().catch(() => null),
        analyticsClient.getSummary().catch(() => null),
      ]);
      setDashboard(data);
      setKycApp(kyc);
      setAnalyticsSummary(summary);
      setError(null);
      setOffline(false);
      writeQueueCache({
        saved_at: new Date().toISOString(),
        dashboard: data,
        queue: data.needs_action,
      });
    } catch (caught) {
      const cached = readQueueCache();
      if (cached?.dashboard) {
        setDashboard(cached.dashboard);
        setOffline(true);
        setError(null);
        setErrorKey(null);
      } else {
        setErrorKey(vendorErrorMessageKey(caught, "home"));
        setError(null);
      }
    } finally {
      setLoading(false);
    }
  }, [analyticsClient, kycClient, queueClient, session]);

  useEffect(() => {
    const cached = readQueueCache();
    if (cached?.dashboard) {
      setDashboard(cached.dashboard);
    }
  }, []);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void load();
  }, [load, session, sessionLoading]);

  useEffect(() => {
    if (!session) {
      setPayoutMissing(null);
      return;
    }
    let cancelled = false;
    void payoutsClient
      .getBalances()
      .then((balances) => {
        if (cancelled) {
          return;
        }
        const msisdn = balances.payout_msisdn?.trim() ?? "";
        setPayoutMissing(msisdn.length === 0);
      })
      .catch(() => {
        if (!cancelled) {
          setPayoutMissing(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [payoutsClient, session]);

  useEffect(() => {
    if (!session) {
      setProductsInReviewCount(0);
      return;
    }
    let cancelled = false;
    void manageClient
      .listListings()
      .then((rows) => {
        if (cancelled) {
          return;
        }
        setProductsInReviewCount(
          rows.filter(
            (row) => row.status === "active" && row.product_status === "pending_moderation",
          ).length,
        );
      })
      .catch(() => {
        if (!cancelled) {
          setProductsInReviewCount(0);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [manageClient, session]);

  if (sessionLoading || (loading && !dashboard)) {
    return <DashboardSkeleton label={t("home.loading")} />;
  }

  if (!session) {
    return (
      <VendorErrorState
        title={t("home.errors.authRequired")}
        retryLabel={tCommon("common.retry")}
      />
    );
  }

  if (errorKey && !dashboard) {
    return (
      <VendorErrorState
        title={t(errorKey as "home.errors.loadFailed")}
        body={t("home.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => void load()}
      />
    );
  }

  const needsCount = dashboard?.queue_counts.needs_action ?? 0;
  const takings = dashboard?.takings_ngwee ?? 0;

  const kycApproved = kycApp
    ? isAuditableApproved({
        kyc_tier: kycApp.kyc_tier,
        kyc_status: kycApp.kyc_status,
        kyc_record_id: kycApp.kyc_record_id,
        kyc_record_status: kycApp.kyc_record_status,
      })
    : false;
  // Home must agree with the stricter auditable check (tier + record status).
  const checklistOverall = kycApp ? buildKycChecklist(kycApp).overall : null;
  const kycOverall = checklistOverall === "approved" && !kycApproved ? "pending" : checklistOverall;
  const waitingOrders = dashboard?.needs_action ?? [];
  const hasDeliveryWaiting = waitingOrders.some((order) => isBoundByDispatchCutoff(order));

  // Prefer the strategy operating archetype. Fall back to the legacy merchandise
  // category for vendors onboarded before that dimension was collected.
  const businessArchetype = dashboard?.business_archetype ?? null;
  const category = dashboard?.archetype ?? null;
  const isServicesVendor =
    businessArchetype === "service_professional" ||
    (businessArchetype === null && category === "services");
  const isEventOrganiser = businessArchetype === "event_organiser";
  let businessType: string | null = null;
  switch (businessArchetype) {
    case "market_trader":
      businessType = t("home.businessArchetypes.market_trader");
      break;
    case "registered_retailer":
      businessType = t("home.businessArchetypes.registered_retailer");
      break;
    case "service_professional":
      businessType = t("home.businessArchetypes.service_professional");
      break;
    case "manufacturer":
      businessType = t("home.businessArchetypes.manufacturer");
      break;
    case "importer_wholesaler":
      businessType = t("home.businessArchetypes.importer_wholesaler");
      break;
    case "event_organiser":
      businessType = t("home.businessArchetypes.event_organiser");
      break;
  }
  if (businessType === null) {
    switch (category) {
      case "electronics":
        businessType = t("home.businessTypes.electronics");
        break;
      case "home":
        businessType = t("home.businessTypes.home");
        break;
      case "fashion_beauty":
        businessType = t("home.businessTypes.fashion_beauty");
        break;
      case "services":
        businessType = t("home.businessTypes.services");
        break;
      case "groceries":
        businessType = t("home.businessTypes.groceries");
        break;
      case "other":
        businessType = t("home.businessTypes.other");
        break;
      default:
        businessType = null;
    }
  }

  const tasks = buildHomeTasks({
    kycOverall,
    needsActionCount: needsCount,
    hasDeliveryWaiting,
    cutoff,
    sellerKind: isServicesVendor ? "services" : isEventOrganiser ? "events" : "products",
    payoutMissing,
    productsInReviewCount,
  });

  const shopLive = kycApproved;

  return (
    <div className="flex flex-col gap-4 pb-4">
      <VendorRouteHeader title={t("home.title")} subtitle={t("home.eyebrow")} />

      <VendorQuickActionGrid locale={locale} />

      <VendorShopStatusCard
        shopLive={shopLive}
        idVerified={kycApproved}
        payoutSet={payoutMissing === null ? null : !payoutMissing}
      />

      <VendorGrid cols="stats">
        <StatCard
          label={t("home.takings.label")}
          value={formatK(takings)}
          icon={<LcTrendingUp className="size-5" duotone aria-hidden />}
          iconHue="teal"
          delta={
            takings > 0
              ? { text: t("home.stats.live"), trend: "up" }
              : { text: t("home.stats.quiet"), trend: "neutral" }
          }
          data-testid="vendor-home-stat-takings"
        />
        <StatCard
          label={t("home.needsAction.heading")}
          value={String(needsCount)}
          icon={<LcClipboardList className="size-5" duotone aria-hidden />}
          iconHue="orange"
          delta={
            needsCount > 0
              ? { text: t("home.stats.actionNeeded"), trend: "down" }
              : { text: t("home.stats.caughtUp"), trend: "up" }
          }
        />
        {analyticsSummary ? (
          <>
            <StatCard
              label={t("home.analytics.views")}
              value={analyticsSummary.total_views.toLocaleString()}
              icon={<LcLayoutGrid className="size-5" duotone aria-hidden />}
              iconHue="blue"
            />
            <StatCard
              label={t("home.analytics.gmv")}
              value={formatK(analyticsSummary.gmv_ngwee)}
              icon={<LcShoppingBag className="size-5" duotone aria-hidden />}
              iconHue="green"
            />
          </>
        ) : (
          <>
            <StatCard
              label={t("home.analytics.orders")}
              value="—"
              icon={<LcShoppingBag className="size-5" duotone aria-hidden />}
              iconHue="slate"
            />
            <StatCard
              label={t("home.analytics.gmv")}
              value="—"
              icon={<LcTrendingUp className="size-5" duotone aria-hidden />}
              iconHue="slate"
            />
          </>
        )}
      </VendorGrid>

      {offline ? (
        <p className="rounded-md bg-warning/10 px-3 py-2 text-sm text-text" role="status">
          {t("home.offlineNotice")}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <VendorGrid cols="two">
        <HomeTaskList locale={locale} tasks={tasks} />

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="mb-2 text-lg font-semibold text-text">
              {t("home.needsAction.heading")}
            </h2>
            {needsCount > 0 ? (
              <span className="rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">
                {needsCount}
              </span>
            ) : null}
          </div>

          {!dashboard || dashboard.needs_action.length === 0 ? (
            <VendorEmptyState
              title={t("home.needsAction.emptyTitle")}
              body={t("home.needsAction.empty")}
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {dashboard.needs_action.map((order) => (
                <OrderCard
                  key={order.id}
                  locale={locale}
                  order={order}
                  onError={setError}
                  onUpdated={() => void load()}
                />
              ))}
            </ul>
          )}
        </section>
      </VendorGrid>

      {businessType ? (
        <section className="rounded-2xl border border-border bg-surface p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-3">
            {t("home.quickStart.eyebrow", { businessType })}
          </p>
          {isServicesVendor ? (
            <>
              <h2 className="mt-1 text-sm font-semibold text-text">
                {t("home.quickStart.services.heading")}
              </h2>
              <p className="mt-1 text-sm text-text-2">{t("home.quickStart.services.body")}</p>
              <Link
                className="mt-3 inline-flex min-h-11 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)]"
                href={`/${locale}/services`}
              >
                {t("home.quickStart.services.cta")}
              </Link>
            </>
          ) : isEventOrganiser ? (
            <>
              <h2 className="mt-1 text-sm font-semibold text-text">
                {t("home.quickStart.events.heading")}
              </h2>
              <p className="mt-1 text-sm text-text-2">{t("home.quickStart.events.body")}</p>
              <Link
                className="mt-3 inline-flex min-h-11 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)]"
                href={`/${locale}/events`}
              >
                {t("home.quickStart.events.cta")}
              </Link>
            </>
          ) : (
            <>
              <h2 className="mt-1 text-sm font-semibold text-text">
                {t("home.quickStart.products.heading")}
              </h2>
              <p className="mt-1 text-sm text-text-2">{t("home.quickStart.products.body")}</p>
              <Link
                className="mt-3 inline-flex min-h-11 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)]"
                href={`/${locale}/listings`}
              >
                {t("home.quickStart.products.cta")}
              </Link>
            </>
          )}
        </section>
      ) : null}

      <section className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom,0px)+0.5rem)] z-10 grid grid-cols-1 gap-2 border-t border-border bg-bg/90 px-1 py-3 backdrop-blur-sm lg:static lg:border-0 lg:bg-transparent lg:py-0 lg:backdrop-blur-none">
        <Link
          className="press-scale inline-flex min-h-12 items-center justify-center rounded-xl bg-primary px-4 text-base font-semibold text-[var(--primary-btn-fg)] shadow-1"
          href={`/${locale}/orders`}
        >
          {t("home.actions.openQueue")}
        </Link>
        <Link
          className="press-scale inline-flex min-h-11 items-center justify-center rounded-xl border border-border bg-surface px-4 text-sm font-medium text-text"
          href={`/${locale}/orders?status=placed`}
        >
          {t("home.actions.confirmOrders")}
        </Link>
      </section>
    </div>
  );
}
