"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { HomeTaskList } from "../../_components/home-tasks";
import { VendorGrid } from "../../_components/vendor-page";
import { VendorQuickActionGrid } from "../../_components/vendor-quick-action-grid";
import { VendorRouteHeader } from "../../_components/vendor-route-header";
import { DashboardSkeleton, ListSkeleton } from "../../_components/vendor-skeletons";
import { buildHomeTasks } from "../../_lib/home-tasks";
import { isAuditableApproved } from "../../_lib/kyc-integrity";
import { vendorErrorMessageKey } from "../../_lib/vendor-errors";
import {
  createAnalyticsClient,
  type VendorAnalyticsSummary,
} from "../../analytics/_lib/analytics-client";
import {
  Button,
  FormField,
  Input,
  orderStatusTone,
  PriceBlock,
  StatusChip,
} from "../../listings/new/_lib/ui";
import { buildKycChecklist } from "../../onboarding/_lib/kyc-checklist";
import { createKycClient } from "../../onboarding/_lib/kyc-client";
import { createPayoutsClient } from "../../payouts/_lib/payouts-client";
import { isBoundByDispatchCutoff } from "../_lib/order-guidance";

import { DispatchCutoffBanner, OrderNextStepHint, useDispatchCutoff } from "./order-guidance";

import type { OrderActionResponse, VendorActionName } from "./action-bar";
import type { KycApplication } from "../../onboarding/_lib/types";

export type OrderQueueItem = {
  id: string;
  status: string;
  fulfilment: string;
  total_ngwee: number;
  item_count: number;
  preview_title: string;
  created_at: string;
  available_actions: VendorActionName[];
  urgency: number;
};

export type VendorDashboard = {
  takings_ngwee: number;
  takings_date: string;
  needs_action: OrderQueueItem[];
  queue_counts: Record<string, number>;
  archetype?: string | null;
  business_archetype?: string | null;
};

const CACHE_KEY = "vergeo5.vendor.orders.queue.v1";
const CARD_ACTIONS: VendorActionName[] = [
  "confirm",
  "pack",
  "ready_for_collection",
  "ship",
  "ready_for_pickup",
];

type QueueCache = {
  saved_at: string;
  dashboard: VendorDashboard | null;
  queue: OrderQueueItem[] | null;
};

export function createOrdersQueueClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getDashboard(): Promise<VendorDashboard> {
      return client.request<VendorDashboard>("/vendor/orders/dashboard");
    },
    listQueue(status: string): Promise<OrderQueueItem[]> {
      const query = new URLSearchParams({ status });
      return client.request<OrderQueueItem[]>(`/vendor/orders/queue?${query.toString()}`);
    },
    confirm(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/confirm`, {
        method: "POST",
      });
    },
    pack(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/pack`, {
        method: "POST",
      });
    },
    ship(orderId: string, trackingNote: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/ship`, {
        method: "POST",
        body: JSON.stringify({ tracking_note: trackingNote }),
      });
    },
    readyForPickup(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/ready-for-pickup`, {
        method: "POST",
      });
    },
    readyForCollection(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/ready-for-collection`, {
        method: "POST",
      });
    },
  };
}

export function readQueueCache(): QueueCache | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as QueueCache;
  } catch {
    return null;
  }
}

export function writeQueueCache(payload: QueueCache): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore quota / private-mode failures.
  }
}

function primaryCardAction(actions: VendorActionName[]): VendorActionName | null {
  for (const action of CARD_ACTIONS) {
    if (actions.includes(action)) {
      return action;
    }
  }
  return null;
}

const ACTION_LABEL_KEYS: Record<VendorActionName, string> = {
  confirm: "orders.actions.confirm",
  reject: "orders.actions.reject",
  pack: "orders.actions.pack",
  ship: "orders.actions.ship",
  ready_for_pickup: "orders.actions.ready_for_pickup",
  ready_for_collection: "orders.actions.ready_for_collection",
};

const ACTION_PENDING_KEYS: Record<VendorActionName, string> = {
  confirm: "orders.actions.confirming",
  reject: "orders.actions.rejecting",
  pack: "orders.actions.packing",
  ship: "orders.actions.shipping",
  ready_for_pickup: "orders.actions.markingReady",
  ready_for_collection: "orders.actions.markingReady",
};

type OrderCardProps = {
  locale: string;
  order: OrderQueueItem;
  onUpdated: (response: OrderActionResponse) => void;
  onError: (message: string) => void;
};

export function OrderCard({ locale, order, onUpdated, onError }: OrderCardProps) {
  const t = useTranslations("vendor");
  const { session } = useSession();
  const [pending, setPending] = useState(false);
  const [sheetAction, setSheetAction] = useState<VendorActionName | null>(null);
  const [trackingNote, setTrackingNote] = useState("");

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const queueClient = useMemo(() => createOrdersQueueClient(getToken), [getToken]);

  const action = primaryCardAction(order.available_actions);

  const statusLabel = (() => {
    const key = `orders.status.${order.status}` as const;
    try {
      return t(key);
    } catch {
      return order.status;
    }
  })();

  const runAction = async (nextAction: VendorActionName) => {
    if (!session) {
      return;
    }
    setPending(true);
    try {
      let response: OrderActionResponse;
      switch (nextAction) {
        case "confirm":
          response = await queueClient.confirm(order.id);
          break;
        case "pack":
          response = await queueClient.pack(order.id);
          break;
        case "ship":
          if (!trackingNote.trim()) {
            onError(t("orders.errors.trackingRequired"));
            return;
          }
          response = await queueClient.ship(order.id, trackingNote.trim());
          break;
        case "ready_for_pickup":
          response = await queueClient.readyForPickup(order.id);
          break;
        case "ready_for_collection":
          response = await queueClient.readyForCollection(order.id);
          break;
        default:
          return;
      }
      setSheetAction(null);
      setTrackingNote("");
      onUpdated(response);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "order_invalid_transition") {
          onError(t("orders.errors.invalidTransition"));
        } else if (error.status === 403) {
          onError(t("orders.errors.forbidden"));
        } else {
          onError(t("orders.errors.actionFailed"));
        }
      } else {
        onError(t("orders.errors.actionFailed"));
      }
    } finally {
      setPending(false);
    }
  };

  const openSheet = (nextAction: VendorActionName) => {
    if (nextAction === "ship") {
      setSheetAction("ship");
      return;
    }
    setSheetAction(nextAction);
  };

  return (
    <li className="rounded-xl border border-border bg-surface p-3 shadow-sm">
      <div className="flex items-start gap-3">
        <Link
          className="min-w-0 flex-1"
          href={`/${locale}/orders/${order.id}`}
          data-testid="vendor-order-card-link"
          data-order-id={order.id}
          data-order-status={order.status}
        >
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-semibold text-text">{order.preview_title}</p>
            <StatusChip tone={orderStatusTone(order.status)} label={statusLabel} />
          </div>
          <p className="mt-1 text-xs text-text-3">
            {t("queue.card.items", { count: order.item_count })}
          </p>
          <OrderNextStepHint order={order} />
          <p className="mt-1 text-sm font-medium text-text">
            <PriceBlock ngwee={order.total_ngwee} />
          </p>
        </Link>

        {action ? (
          <Button
            type="button"
            className="min-h-12 min-w-[5.5rem] shrink-0 px-3 text-sm"
            loading={pending}
            loadingLabel={t(ACTION_PENDING_KEYS[action])}
            onClick={() => openSheet(action)}
          >
            {t(ACTION_LABEL_KEYS[action])}
          </Button>
        ) : null}
      </div>

      {sheetAction ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => {
            if (!pending) {
              setSheetAction(null);
            }
          }}
        >
          <div
            className="w-full max-w-[360px] rounded-t-2xl bg-surface p-4 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`order-sheet-${order.id}`}
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id={`order-sheet-${order.id}`} className="text-base font-semibold text-text">
              {t("queue.sheet.title", {
                action: t(ACTION_LABEL_KEYS[sheetAction]),
              })}
            </h3>
            <p className="mt-2 text-sm text-text-2">
              {t("queue.sheet.body", {
                title: order.preview_title,
                amount: formatK(order.total_ngwee),
              })}
            </p>

            {sheetAction === "ship" ? (
              <div className="mt-3">
                <FormField label={t("orders.actions.shipLabel")} id={`tracking-${order.id}`}>
                  <Input
                    value={trackingNote}
                    onChange={(event) => setTrackingNote(event.target.value)}
                    placeholder={t("orders.actions.shipPlaceholder")}
                  />
                </FormField>
              </div>
            ) : null}

            <div className="mt-4 flex flex-col gap-2">
              <Button
                type="button"
                className="min-h-12 w-full text-base"
                loading={pending}
                loadingLabel={t(ACTION_PENDING_KEYS[sheetAction])}
                onClick={() => void runAction(sheetAction)}
              >
                {t("queue.sheet.confirm")}
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="min-h-11 w-full"
                loadingLabel=""
                disabled={pending}
                onClick={() => setSheetAction(null)}
              >
                {t("queue.sheet.cancel")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </li>
  );
}

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
          <VendorGrid cols="cards">
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
  const cutoff = useDispatchCutoff();

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const queueClient = useMemo(() => createOrdersQueueClient(getToken), [getToken]);
  const kycClient = useMemo(() => createKycClient(getToken), [getToken]);
  const analyticsClient = useMemo(() => createAnalyticsClient(getToken), [getToken]);
  const payoutsClient = useMemo(() => createPayoutsClient(getToken), [getToken]);

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
  });

  return (
    <div className="flex flex-col gap-4 pb-4">
      <VendorRouteHeader title={t("home.title")} subtitle={t("home.eyebrow")} />

      <VendorQuickActionGrid locale={locale} />

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
