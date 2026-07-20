"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { Badge, Button, FormField, Input, PriceBlock, Spinner } from "../../listings/new/_lib/ui";

export type VendorActionName = "confirm" | "reject" | "pack" | "ship" | "ready_for_pickup";

export type OrderItemSummary = {
  id: string;
  title: string;
  qty: number;
  unit_price_ngwee: number;
};

export type OrderEventSummary = {
  id: string;
  from_status: string | null;
  to_status: string;
  note: string | null;
  created_at: string;
  actor: string | null;
};

export type OrderDetail = {
  id: string;
  status: string;
  fulfilment: string;
  cod: boolean;
  paid: boolean;
  delivery_fee_ngwee: number;
  created_at: string;
  customer_id: string;
  items: OrderItemSummary[];
  timeline: OrderEventSummary[];
  available_actions: VendorActionName[];
};

export type OrderActionResponse = {
  order_id: string;
  from_status: string;
  to_status: string;
  event: string;
  available_actions: VendorActionName[];
};

function createOrdersClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getOrder(orderId: string): Promise<OrderDetail> {
      return client.request<OrderDetail>(`/vendor/orders/${orderId}`);
    },
    confirm(orderId: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/confirm`, {
        method: "POST",
      });
    },
    reject(orderId: string, reason: string): Promise<OrderActionResponse> {
      return client.request<OrderActionResponse>(`/vendor/orders/${orderId}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason }),
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

type OrderActionBarProps = {
  orderId: string;
  availableActions: VendorActionName[];
  onActionComplete: (response: OrderActionResponse) => void;
  onError: (message: string) => void;
};

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

export function OrderActionBar({
  orderId,
  availableActions,
  onActionComplete,
  onError,
}: OrderActionBarProps) {
  const t = useTranslations("vendor");
  const { session } = useSession();
  const [pendingAction, setPendingAction] = useState<VendorActionName | null>(null);
  const [expandedAction, setExpandedAction] = useState<"reject" | "ship" | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [trackingNote, setTrackingNote] = useState("");

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const ordersClient = useMemo(() => createOrdersClient(getToken), [getToken]);

  if (availableActions.length === 0) {
    return null;
  }

  const runAction = async (action: VendorActionName) => {
    if (!session) {
      return;
    }
    setPendingAction(action);
    try {
      let response: OrderActionResponse;
      switch (action) {
        case "confirm":
          response = await ordersClient.confirm(orderId);
          break;
        case "reject":
          if (!rejectReason.trim()) {
            onError(t("orders.errors.reasonRequired"));
            return;
          }
          response = await ordersClient.reject(orderId, rejectReason.trim());
          break;
        case "pack":
          response = await ordersClient.pack(orderId);
          break;
        case "ship":
          if (!trackingNote.trim()) {
            onError(t("orders.errors.trackingRequired"));
            return;
          }
          response = await ordersClient.ship(orderId, trackingNote.trim());
          break;
        case "ready_for_pickup":
          response = await ordersClient.readyForPickup(orderId);
          break;
      }
      setExpandedAction(null);
      setRejectReason("");
      setTrackingNote("");
      onActionComplete(response);
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
      setPendingAction(null);
    }
  };

  const handlePrimaryClick = (action: VendorActionName) => {
    if (action === "reject") {
      setExpandedAction((current) => (current === "reject" ? null : "reject"));
      return;
    }
    if (action === "ship") {
      setExpandedAction((current) => (current === "ship" ? null : "ship"));
      return;
    }
    void runAction(action);
  };

  return (
    <section className="flex flex-col gap-3 border-t border-border pt-4">
      <h2 className="text-sm font-semibold text-text">{t("orders.actions.heading")}</h2>

      {expandedAction === "reject" ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-bg-2 p-3">
          <p className="text-sm text-text-2">{t("orders.actions.rejectPrompt")}</p>
          <FormField label={t("orders.actions.rejectLabel")} id="reject-reason">
            <Input
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              placeholder={t("orders.actions.rejectPlaceholder")}
            />
          </FormField>
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              className="min-h-12 w-full text-base"
              loading={pendingAction === "reject"}
              loadingLabel={t("orders.actions.rejecting")}
              disabled={pendingAction !== null && pendingAction !== "reject"}
              onClick={() => void runAction("reject")}
            >
              {t("orders.actions.submitReject")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="min-h-11 w-full"
              loadingLabel=""
              onClick={() => setExpandedAction(null)}
            >
              {t("orders.actions.cancel")}
            </Button>
          </div>
        </div>
      ) : null}

      {expandedAction === "ship" ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-bg-2 p-3">
          <p className="text-sm text-text-2">{t("orders.actions.shipPrompt")}</p>
          <FormField label={t("orders.actions.shipLabel")} id="tracking-note">
            <Input
              value={trackingNote}
              onChange={(event) => setTrackingNote(event.target.value)}
              placeholder={t("orders.actions.shipPlaceholder")}
            />
          </FormField>
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              className="min-h-12 w-full text-base"
              loading={pendingAction === "ship"}
              loadingLabel={t("orders.actions.shipping")}
              disabled={pendingAction !== null && pendingAction !== "ship"}
              onClick={() => void runAction("ship")}
            >
              {t("orders.actions.submitShip")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="min-h-11 w-full"
              loadingLabel=""
              onClick={() => setExpandedAction(null)}
            >
              {t("orders.actions.cancel")}
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        {availableActions.map((action) => {
          if (expandedAction === "reject" && action === "reject") {
            return null;
          }
          if (expandedAction === "ship" && action === "ship") {
            return null;
          }
          const isDestructive = action === "reject";
          return (
            <Button
              key={action}
              type="button"
              variant={isDestructive ? "secondary" : "primary"}
              className="min-h-12 w-full text-base"
              loading={pendingAction === action}
              loadingLabel={t(ACTION_PENDING_KEYS[action])}
              disabled={pendingAction !== null && pendingAction !== action}
              onClick={() => handlePrimaryClick(action)}
            >
              {t(ACTION_LABEL_KEYS[action])}
            </Button>
          );
        })}
      </div>
    </section>
  );
}

type OrderDetailViewProps = {
  orderId: string;
};

export function OrderDetailView({ orderId }: OrderDetailViewProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const ordersClient = useMemo(() => createOrdersClient(getToken), [getToken]);

  const statusLabel = useCallback(
    (status: string) => {
      const key = `orders.status.${status}` as const;
      try {
        return t(key);
      } catch {
        return status;
      }
    },
    [t],
  );

  const loadOrder = useCallback(async () => {
    setLoading(true);
    try {
      const detail = await ordersClient.getOrder(orderId);
      setOrder(detail);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("orders.errors.forbidden"));
      } else {
        setError(t("orders.errors.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [orderId, ordersClient, t]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadOrder();
  }, [loadOrder, session, sessionLoading]);

  const handleActionComplete = (response: OrderActionResponse) => {
    setOrder((current) =>
      current
        ? {
            ...current,
            status: response.to_status,
            available_actions: response.available_actions,
          }
        : current,
    );
    const successKey = `orders.success.${
      response.event === "confirm"
        ? "confirmed"
        : response.event === "reject"
          ? "rejected"
          : response.event === "start_processing"
            ? "packed"
            : response.event === "ship"
              ? "shipped"
              : "ready"
    }` as const;
    setSuccess(t(successKey));
    setError(null);
    void loadOrder();
  };

  if (sessionLoading || loading) {
    return (
      <div className="flex flex-1 items-center justify-center py-16">
        <Spinner label={t("orders.loading")} />
      </div>
    );
  }

  if (error && !order) {
    return <p className="py-8 text-center text-sm text-danger">{error}</p>;
  }

  if (!order) {
    return null;
  }

  const paymentLabel = order.cod
    ? t("orders.payment.cod")
    : order.paid
      ? t("orders.payment.paid")
      : t("orders.payment.unpaid");

  const fulfilmentLabel =
    order.fulfilment === "pickup" ? t("orders.fulfilment.pickup") : t("orders.fulfilment.delivery");

  return (
    <div className="flex flex-col gap-5 pb-8">
      <header className="flex flex-col gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-text-2">
          {t("orders.title")}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-text">{statusLabel(order.status)}</h1>
          <Badge variant="public" label={fulfilmentLabel} />
        </div>
        <p className="text-xs text-text-2">{order.id}</p>
      </header>

      {success ? (
        <p className="rounded-md bg-success/10 px-3 py-2 text-sm text-success">{success}</p>
      ) : null}
      {error ? (
        <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>
      ) : null}

      <section className="flex flex-col gap-2 rounded-lg border border-border p-3">
        <h2 className="text-sm font-semibold text-text">{t("orders.payment.heading")}</h2>
        <p className="text-sm text-text-2">{paymentLabel}</p>
        {order.delivery_fee_ngwee > 0 ? (
          <p className="text-sm text-text-2">
            <PriceBlock ngwee={order.delivery_fee_ngwee} />
          </p>
        ) : null}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-text">{t("orders.items.heading")}</h2>
        {order.items.length === 0 ? (
          <p className="text-sm text-text-2">{t("orders.items.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {order.items.map((item) => (
              <li
                key={item.id}
                className="flex items-start justify-between gap-3 rounded-lg border border-border p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-text">{item.title}</p>
                  <p className="text-sm text-text-2">{t("orders.items.qty", { qty: item.qty })}</p>
                </div>
                <PriceBlock ngwee={item.unit_price_ngwee * item.qty} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-text">{t("orders.timeline.heading")}</h2>
        {order.timeline.length === 0 ? (
          <p className="text-sm text-text-2">{t("orders.timeline.empty")}</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {order.timeline.map((event) => (
              <li key={event.id} className="rounded-lg border border-border p-3">
                <p className="text-sm font-medium text-text">{statusLabel(event.to_status)}</p>
                {event.note ? (
                  <p className="mt-1 text-sm text-text-2">
                    {t("orders.timeline.note", { note: event.note })}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>

      <OrderActionBar
        orderId={orderId}
        availableActions={order.available_actions}
        onActionComplete={handleActionComplete}
        onError={setError}
      />
    </div>
  );
}
