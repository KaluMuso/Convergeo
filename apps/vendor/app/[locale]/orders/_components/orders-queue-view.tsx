"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { VendorGrid } from "../../_components/vendor-page";
import { VendorRouteHeader } from "../../_components/vendor-route-header";
import { ListSkeleton } from "../../_components/vendor-skeletons";
import { isBoundByDispatchCutoff } from "../_lib/order-guidance";

import { OrderCard } from "./order-card";
import { DispatchCutoffBanner, useDispatchCutoff } from "./order-guidance";
import {
  createOrdersQueueClient,
  readQueueCache,
  writeQueueCache,
  type OrderQueueItem,
} from "./orders-queue-client";

type PullToRefreshListProps = {
  children: React.ReactNode;
  onRefresh: () => Promise<void>;
  label: string;
};

export function PullToRefreshList({ children, onRefresh, label }: PullToRefreshListProps) {
  const [pulling, setPulling] = useState(false);
  const startY = useRef(0);

  return (
    <div
      className="flex flex-1 flex-col"
      onTouchStart={(event) => {
        if (window.scrollY <= 0) {
          startY.current = event.touches[0]?.clientY ?? 0;
        }
      }}
      onTouchMove={(event) => {
        if (startY.current <= 0) {
          return;
        }
        const delta = (event.touches[0]?.clientY ?? 0) - startY.current;
        if (delta > 72) {
          setPulling(true);
        }
      }}
      onTouchEnd={() => {
        if (pulling) {
          void onRefresh().finally(() => setPulling(false));
        }
        startY.current = 0;
        setPulling(false);
      }}
    >
      {pulling ? <p className="py-2 text-center text-xs text-text-3">{label}</p> : null}
      {children}
    </div>
  );
}

type OrdersQueueViewProps = {
  locale: string;
  initialStatus?: string;
};

export function OrdersQueueView({ locale, initialStatus = "needs_action" }: OrdersQueueViewProps) {
  const t = useTranslations("vendor");
  const tCommon = useTranslations("common");
  const { session, loading: sessionLoading } = useSession();
  const cutoff = useDispatchCutoff();
  const [statusFilter, setStatusFilter] = useState(initialStatus);
  const [orders, setOrders] = useState<OrderQueueItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const queueClient = useMemo(() => createOrdersQueueClient(getToken), [getToken]);

  const load = useCallback(
    async (opts?: { background?: boolean }) => {
      if (!session) {
        return;
      }
      if (opts?.background) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      try {
        const [dashboard, queue] = await Promise.all([
          queueClient.getDashboard(),
          queueClient.listQueue(statusFilter),
        ]);
        setOrders(queue);
        setCounts(dashboard.queue_counts);
        setError(null);
        setOffline(false);
        writeQueueCache({
          saved_at: new Date().toISOString(),
          dashboard,
          queue,
        });
      } catch {
        const cached = readQueueCache();
        if (cached?.queue) {
          setOrders(cached.queue);
          if (cached.dashboard) {
            setCounts(cached.dashboard.queue_counts);
          }
          setOffline(true);
          setError(null);
        } else {
          setError(t("queue.errors.loadFailed"));
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [queueClient, session, statusFilter, t],
  );

  useEffect(() => {
    const cached = readQueueCache();
    if (cached?.queue) {
      setOrders(cached.queue);
      if (cached.dashboard) {
        setCounts(cached.dashboard.queue_counts);
      }
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

  const filters = [
    { key: "needs_action", label: t("queue.filters.needsAction") },
    { key: "placed", label: t("queue.filters.placed") },
    { key: "confirmed", label: t("queue.filters.confirmed") },
    { key: "processing", label: t("queue.filters.processing") },
    { key: "all", label: t("queue.filters.all") },
  ] as const;

  const handleUpdated = () => {
    void load({ background: true });
  };

  if (sessionLoading || (loading && orders.length === 0)) {
    return <ListSkeleton label={t("queue.loading")} />;
  }

  if (error && orders.length === 0) {
    return (
      <VendorErrorState
        title={error}
        body={t("queue.errors.retryHint")}
        retryLabel={tCommon("common.retry")}
        onRetry={() => void load()}
      />
    );
  }

  const hasCutoffBoundOrder = orders.some((order) => isBoundByDispatchCutoff(order));

  return (
    <PullToRefreshList
      label={t("queue.pullToRefresh")}
      onRefresh={() => load({ background: true })}
    >
      <div className="flex flex-col gap-5 pb-4">
        <VendorRouteHeader title={t("queue.title")} subtitle={t("queue.intro")} />

        {hasCutoffBoundOrder ? <DispatchCutoffBanner cutoff={cutoff} /> : null}

        {offline ? (
          <p className="rounded-md bg-warning/10 px-3 py-2 text-sm text-text" role="status">
            {t("queue.offlineNotice")}
          </p>
        ) : null}
        {error ? (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        ) : null}
        {refreshing ? <p className="text-xs text-text-3">{t("queue.refreshing")}</p> : null}

        <div className="flex gap-2 overflow-x-auto pb-1">
          {filters.map((filter) => {
            const active = statusFilter === filter.key;
            const badge = counts[filter.key];
            return (
              <button
                key={filter.key}
                type="button"
                className={`min-h-11 shrink-0 rounded-full border px-3 text-sm font-medium ${
                  active
                    ? "border-primary bg-primary text-[var(--primary-btn-fg)]"
                    : "border-border bg-surface text-text"
                }`}
                aria-pressed={active}
                onClick={() => setStatusFilter(filter.key)}
              >
                {filter.label}
                {typeof badge === "number" && badge > 0 ? ` (${badge})` : ""}
              </button>
            );
          })}
        </div>

        {orders.length === 0 ? (
          statusFilter === "needs_action" ? (
            <VendorEmptyState
              illustration="no-orders"
              title={t("queue.emptyNeedsAction.title")}
              body={t("queue.emptyNeedsAction.body")}
              action={
                <Link
                  className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
                  href={`/${locale}`}
                >
                  {t("queue.emptyCta")}
                </Link>
              }
              data-testid="vendor-queue-empty"
            />
          ) : (
            <VendorEmptyState
              illustration="no-orders"
              title={t("queue.emptyFiltered.title")}
              body={t("queue.emptyFiltered.body")}
              action={
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
                  onClick={() => setStatusFilter("needs_action")}
                >
                  {t("queue.emptyFiltered.cta")}
                </button>
              }
              data-testid="vendor-queue-empty"
            />
          )
        ) : (
          <VendorGrid cols="cards" as="ul">
            {orders.map((order) => (
              <OrderCard
                key={order.id}
                locale={locale}
                order={order}
                onError={setError}
                onUpdated={handleUpdated}
              />
            ))}
          </VendorGrid>
        )}
      </div>
    </PullToRefreshList>
  );
}
