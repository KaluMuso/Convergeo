"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { glassClass } from "@vergeo/ui/src/glass";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import {
  Button,
  FormField,
  Input,
  orderStatusTone,
  PriceBlock,
  StatusChip,
} from "../../listings/new/_lib/ui";

import { OrderNextStepHint } from "./order-guidance";
import { createOrdersQueueClient, type OrderQueueItem } from "./orders-queue-client";

import type { OrderActionResponse, VendorActionName } from "./action-bar";

const CARD_ACTIONS: VendorActionName[] = [
  "confirm",
  "pack",
  "ready_for_collection",
  "ship",
  "ready_for_pickup",
];

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
          <div className="mt-1 text-sm font-medium text-text">
            <PriceBlock ngwee={order.total_ngwee} />
          </div>
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
            className={`w-full max-w-[360px] rounded-t-2xl p-4 ${glassClass("overlay")}`}
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
