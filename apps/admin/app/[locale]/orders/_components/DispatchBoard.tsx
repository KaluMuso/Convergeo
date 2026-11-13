"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { classifyAdminRequestError } from "../../_components/admin-request";

import { ordersApi } from "./api";
import { CourierManager } from "./CourierManager";
import {
  type Board,
  couriersForOrder,
  groupDispatches,
  type ReadyOrder,
  zonePriceNgwee,
} from "./dispatch-board-model";
import { DispatchCard } from "./DispatchCard";

export function DispatchBoard() {
  const t = useTranslations("admin.dispatch");
  const [board, setBoard] = useState<Board | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await ordersApi.request<Board>("/admin/dispatch/board");
      setBoard(data);
      setError(null);
    } catch (err) {
      const classified = classifyAdminRequestError(err);
      setError(classified.kind === "permission" ? t("errors.permissionDenied") : t("error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !board) {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }

  if (!board) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error ?? t("error")}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
          onClick={() => void load()}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  const { active, closed } = groupDispatches(board.dispatches);
  const reload = () => void load();

  return (
    <div className="space-y-6" data-testid="dispatch-board">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {!board.flag_enabled ? (
          <p
            className="rounded-md border border-warning px-3 py-2 text-sm text-warning"
            role="status"
          >
            {t("disabled")}
          </p>
        ) : (
          <span />
        )}
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm"
          onClick={reload}
          disabled={loading}
        >
          {t("refresh")}
        </button>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <section className="space-y-3" aria-labelledby="dispatch-ready-heading">
        <h2 id="dispatch-ready-heading" className="font-medium text-text">
          {t("ready.title", { count: board.ready_orders.length })}
        </h2>
        {board.ready_orders.length === 0 ? (
          <p className="text-sm text-muted">{t("ready.empty")}</p>
        ) : (
          <ul className="space-y-3">
            {board.ready_orders.map((order) => (
              <ReadyOrderRow key={order.order_id} order={order} board={board} onAssigned={reload} />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3" aria-labelledby="dispatch-active-heading">
        <h2 id="dispatch-active-heading" className="font-medium text-text">
          {t("active.title", { count: active.length })}
        </h2>
        {active.length === 0 ? (
          <p className="text-sm text-muted">{t("active.empty")}</p>
        ) : (
          <ul className="space-y-3">
            {active.map((dispatch) => (
              <DispatchCard
                key={dispatch.id}
                dispatch={dispatch}
                flagEnabled={board.flag_enabled}
                doorPaymentEnabled={Boolean(board.door_payment_enabled)}
                onChanged={reload}
              />
            ))}
          </ul>
        )}
      </section>

      {closed.length > 0 ? (
        <section className="space-y-3" aria-labelledby="dispatch-closed-heading">
          <h2 id="dispatch-closed-heading" className="font-medium text-text">
            {t("active.closedTitle")}
          </h2>
          <ul className="space-y-3">
            {closed.map((dispatch) => (
              <DispatchCard
                key={dispatch.id}
                dispatch={dispatch}
                flagEnabled={board.flag_enabled}
                doorPaymentEnabled={Boolean(board.door_payment_enabled)}
                onChanged={reload}
              />
            ))}
          </ul>
        </section>
      ) : null}

      <CourierManager couriers={board.couriers} zones={board.zones} onChanged={reload} />
    </div>
  );
}

const ASSIGN_ERROR_KEYS: Record<string, string> = {
  courier_zone_not_served: "errors.zoneNotServed",
  dispatch_already_active: "errors.alreadyActive",
  order_payment_required: "errors.paymentRequired",
  dispatch_order_not_ready: "errors.orderNotReady",
  courier_inactive: "errors.courierInactive",
};

type ReadyOrderRowProps = {
  order: ReadyOrder;
  board: Board;
  onAssigned: () => void;
};

function ReadyOrderRow({ order, board, onAssigned }: ReadyOrderRowProps) {
  const t = useTranslations("admin.dispatch");
  const options = couriersForOrder(board.couriers, order.delivery_zone);
  const [courierId, setCourierId] = useState(options[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assign = async () => {
    if (!courierId) return;
    setBusy(true);
    setError(null);
    try {
      await ordersApi.request("/admin/dispatch/requests", {
        method: "POST",
        body: JSON.stringify({ order_id: order.order_id, courier_partner_id: courierId }),
      });
      onAssigned();
    } catch (err) {
      if (err instanceof ApiError && err.code === "feature_disabled") {
        setError(t("errors.disabled"));
      } else if (classifyAdminRequestError(err).kind === "permission") {
        setError(t("errors.permissionDenied"));
      } else {
        const known = err instanceof ApiError ? ASSIGN_ERROR_KEYS[err.code] : undefined;
        setError(t(known ?? "errors.generic"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      className="space-y-3 rounded-md border border-border p-4"
      data-testid={`ready-order-${order.order_id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="font-mono text-sm text-text">{order.order_reference}</p>
          <p className="text-xs text-muted">
            {t("ready.meta", {
              vendor: order.vendor_name,
              zone: order.delivery_zone ?? t("ready.zoneUnknown"),
              items: order.item_count,
            })}
          </p>
          {order.last_failed_reason ? (
            <p className="text-xs text-warning">
              {t("ready.lastFailed", { reason: order.last_failed_reason })}
            </p>
          ) : null}
        </div>
        <span className="text-sm font-medium text-text">
          {order.cod
            ? t("ready.cod", { amount: formatK(order.cod_amount_ngwee) })
            : t("ready.prepaid")}
        </span>
      </div>

      {options.length === 0 ? (
        <p className="text-sm text-muted">{t("ready.noCouriers")}</p>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <label className="block flex-1 space-y-1 text-sm">
            <span className="text-muted">{t("ready.courierLabel")}</span>
            <select
              className="min-h-11 w-full rounded-md border border-border px-3"
              value={courierId}
              onChange={(change) => setCourierId(change.target.value)}
            >
              {options.map((courier) => {
                const price = zonePriceNgwee(courier, order.delivery_zone);
                return (
                  <option key={courier.id} value={courier.id}>
                    {price === null
                      ? t("ready.courierOption", { name: courier.name })
                      : t("ready.courierOptionPrice", {
                          name: courier.name,
                          price: formatK(price),
                        })}
                  </option>
                );
              })}
            </select>
          </label>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
            disabled={busy || !courierId || !board.flag_enabled}
            onClick={() => void assign()}
          >
            {busy ? t("ready.assigning") : t("ready.assign")}
          </button>
        </div>
      )}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </li>
  );
}
