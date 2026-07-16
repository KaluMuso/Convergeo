"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge, Button, FormField, Input, PriceBlock, Spinner } from "../../listings/new/_lib/ui";

import type { OrderActionResponse, VendorActionName } from "./action-bar";

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
};

const CACHE_KEY = "vergeo5.vendor.orders.queue.v1";
const CARD_ACTIONS: VendorActionName[] = ["confirm", "pack", "ship", "ready_for_pickup"];

type QueueCache = {
  saved_at: string;
  dashboard: VendorDashboard | null;
  queue: OrderQueueItem[] | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

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
};

const ACTION_PENDING_KEYS: Record<VendorActionName, string> = {
  confirm: "orders.actions.confirming",
  reject: "orders.actions.rejecting",
  pack: "orders.actions.packing",
  ship: "orders.actions.shipping",
  ready_for_pickup: "orders.actions.markingReady",
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
    <li className="rounded-xl border border-neutral-200 bg-white p-3 shadow-sm">
      <div className="flex items-start gap-3">
        <Link className="min-w-0 flex-1" href={`/${locale}/orders/${order.id}`}>
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-semibold text-neutral-900">{order.preview_title}</p>
            <Badge variant="public" label={statusLabel} />
          </div>
          <p className="mt-1 text-xs text-neutral-500">
            {t("queue.card.items", { count: order.item_count })}
          </p>
          <p className="mt-1 text-sm font-medium text-neutral-900">
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
            className="w-full max-w-[360px] rounded-t-2xl bg-white p-4 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`order-sheet-${order.id}`}
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id={`order-sheet-${order.id}`} className="text-base font-semibold text-neutral-900">
              {t("queue.sheet.title", { action: t(ACTION_LABEL_KEYS[sheetAction]) })}
            </h3>
            <p className="mt-2 text-sm text-neutral-600">
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
      {pulling ? <p className="py-2 text-center text-xs text-neutral-500">{label}</p> : null}
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
  const { session, loading: sessionLoading } = useSession();
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

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-40 items-center justify-center">
        <Spinner label={t("queue.loading")} />
      </div>
    );
  }

  return (
    <PullToRefreshList
      label={t("queue.pullToRefresh")}
      onRefresh={() => load({ background: true })}
    >
      <div className="flex flex-col gap-4 pb-8">
        <header className="space-y-1">
          <h1 className="text-xl font-semibold text-neutral-900">{t("queue.title")}</h1>
          <p className="text-sm text-neutral-600">{t("queue.intro")}</p>
        </header>

        {offline ? (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
            {t("queue.offlineNotice")}
          </p>
        ) : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        {refreshing ? <p className="text-xs text-neutral-500">{t("queue.refreshing")}</p> : null}

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
                    ? "border-neutral-900 bg-neutral-900 text-white"
                    : "border-neutral-300 bg-white text-neutral-800"
                }`}
                onClick={() => setStatusFilter(filter.key)}
              >
                {filter.label}
                {typeof badge === "number" && badge > 0 ? ` (${badge})` : ""}
              </button>
            );
          })}
        </div>

        {orders.length === 0 ? (
          <div className="rounded-lg border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-600">
            <p>{t("queue.empty")}</p>
            <Link
              className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-neutral-900"
              href={`/${locale}`}
            >
              {t("queue.emptyCta")}
            </Link>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {orders.map((order) => (
              <OrderCard
                key={order.id}
                locale={locale}
                order={order}
                onError={setError}
                onUpdated={handleUpdated}
              />
            ))}
          </ul>
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
  const { session, loading: sessionLoading } = useSession();
  const [dashboard, setDashboard] = useState<VendorDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const queueClient = useMemo(() => createOrdersQueueClient(getToken), [getToken]);

  const load = useCallback(async () => {
    if (!session) {
      return;
    }
    setLoading(true);
    try {
      const data = await queueClient.getDashboard();
      setDashboard(data);
      setError(null);
      setOffline(false);
      writeQueueCache({
        saved_at: new Date().toISOString(),
        dashboard: data,
        queue: data.needs_action,
      });
    } catch {
      const cached = readQueueCache();
      if (cached?.dashboard) {
        setDashboard(cached.dashboard);
        setOffline(true);
        setError(null);
      } else {
        setError(t("home.errors.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [queueClient, session, t]);

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

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-40 items-center justify-center">
        <Spinner label={t("home.loading")} />
      </div>
    );
  }

  const needsCount = dashboard?.queue_counts.needs_action ?? 0;

  // Archetype-driven guidance: the persisted onboarding business type (migration
  // 0038) tailors the vendor's primary workflow — service providers manage
  // services + quote requests; product sellers manage catalogue listings.
  const archetype = dashboard?.archetype ?? null;
  const isServicesVendor = archetype === "services";
  let businessType: string | null = null;
  switch (archetype) {
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

  return (
    <div className="flex flex-col gap-5 pb-8">
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {t("home.eyebrow")}
        </p>
        <h1 className="text-xl font-semibold text-neutral-900">{t("home.title")}</h1>
      </header>

      {offline ? (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t("home.offlineNotice")}
        </p>
      ) : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      <section className="rounded-2xl bg-neutral-900 p-4 text-white">
        <p className="text-sm text-neutral-200">{t("home.takings.label")}</p>
        <p className="mt-1 font-mono text-3xl font-semibold tracking-tight">
          {formatK(dashboard?.takings_ngwee ?? 0)}
        </p>
        <p className="mt-1 text-xs text-neutral-300">
          {t("home.takings.caption", { date: dashboard?.takings_date ?? "—" })}
        </p>
      </section>

      {businessType ? (
        <section className="rounded-2xl border border-neutral-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            {t("home.quickStart.eyebrow", { businessType })}
          </p>
          {isServicesVendor ? (
            <>
              <h2 className="mt-1 text-sm font-semibold text-neutral-900">
                {t("home.quickStart.services.heading")}
              </h2>
              <p className="mt-1 text-sm text-neutral-600">{t("home.quickStart.services.body")}</p>
              <Link
                className="mt-3 inline-flex min-h-11 items-center justify-center rounded-xl bg-neutral-900 px-4 text-sm font-semibold text-white"
                href={`/${locale}/services`}
              >
                {t("home.quickStart.services.cta")}
              </Link>
            </>
          ) : (
            <>
              <h2 className="mt-1 text-sm font-semibold text-neutral-900">
                {t("home.quickStart.products.heading")}
              </h2>
              <p className="mt-1 text-sm text-neutral-600">{t("home.quickStart.products.body")}</p>
              <Link
                className="mt-3 inline-flex min-h-11 items-center justify-center rounded-xl bg-neutral-900 px-4 text-sm font-semibold text-white"
                href={`/${locale}/listings`}
              >
                {t("home.quickStart.products.cta")}
              </Link>
            </>
          )}
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-neutral-900">
            {t("home.needsAction.heading")}
          </h2>
          {needsCount > 0 ? (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
              {needsCount}
            </span>
          ) : null}
        </div>

        {!dashboard || dashboard.needs_action.length === 0 ? (
          <p className="rounded-lg border border-dashed border-neutral-300 p-4 text-sm text-neutral-600">
            {t("home.needsAction.empty")}
          </p>
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

      <section className="grid grid-cols-1 gap-3">
        <Link
          className="inline-flex min-h-14 items-center justify-center rounded-xl bg-neutral-900 px-4 text-base font-semibold text-white"
          href={`/${locale}/orders`}
        >
          {t("home.actions.openQueue")}
        </Link>
        <Link
          className="inline-flex min-h-12 items-center justify-center rounded-xl border border-neutral-300 px-4 text-sm font-medium text-neutral-900"
          href={`/${locale}/orders?status=placed`}
        >
          {t("home.actions.confirmOrders")}
        </Link>
      </section>
    </div>
  );
}
