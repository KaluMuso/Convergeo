"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { CopyButton } from "../../_components/CopyButton";

import { type OrderDetail, ordersApi } from "./api";
import { parseCourierMessage, type ParsedCourierMessage } from "./courier-message";
import { type Board, type Dispatch } from "./dispatch-board-model";

type Props = {
  locale: string;
  order: OrderDetail;
  /** Dispatch board snapshot; null when it could not be loaded. */
  board: Board | null;
};

/** Cash to collect: the dispatch record is authoritative, else derive from the order. */
export function codAmountNgwee(order: OrderDetail, dispatch: Dispatch | null): number {
  if (dispatch) return dispatch.cod_amount_ngwee;
  if (!order.cod) return 0;
  const items = order.items.reduce((sum, item) => sum + item.unit_price_ngwee * item.qty, 0);
  return items + order.delivery_fee_ngwee;
}

export function pickDispatch(order: OrderDetail, board: Board | null): Dispatch | null {
  const mine = (board?.dispatches ?? []).filter((d) => d.order_id === order.id);
  if (mine.length === 0) return null;
  const open = mine.find((d) => !["failed", "cancelled"].includes(d.status));
  return open ?? mine[mine.length - 1] ?? null;
}

function digits(phone: string): string {
  return phone.replace(/[^\d]/g, "");
}

export function DeliveryCard({ locale, order, board }: Props) {
  const t = useTranslations("admin.orders.delivery");
  const dispatch = pickDispatch(order, board);
  const courier = dispatch
    ? (board?.couriers.find((c) => c.id === dispatch.courier_partner_id) ?? null)
    : null;
  const cod = codAmountNgwee(order, dispatch);
  const [parsed, setParsed] = useState<ParsedCourierMessage | null>(null);
  const [rawMessage, setRawMessage] = useState<string | null>(null);
  const [messageFailed, setMessageFailed] = useState(false);

  useEffect(() => {
    if (!dispatch) return;
    let cancelled = false;
    ordersApi
      .request<{ text: string }>(`/admin/dispatch/requests/${dispatch.id}/message`)
      .then((message) => {
        if (cancelled) return;
        setRawMessage(message.text);
        setParsed(parseCourierMessage(message.text));
      })
      .catch(() => {
        if (!cancelled) setMessageFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch?.id]);

  const phone = order.customer_phone;
  const dropoff = parsed?.dropoff ?? null;
  const addressCopy = dropoff ? [dropoff.text, dropoff.mapsUrl].filter(Boolean).join("\n") : null;

  return (
    <section
      aria-labelledby="delivery-heading"
      className="space-y-4 rounded-lg border border-border bg-surface p-4"
      data-testid="delivery-card"
    >
      <h2 id="delivery-heading" className="font-medium text-text">
        {order.fulfilment === "pickup" ? t("titlePickup") : t("title")}
      </h2>

      <div
        className={`rounded-md border p-3 ${cod > 0 ? "border-warning/50 bg-warning/5" : "border-border bg-bg"}`}
        data-testid="cod-amount"
      >
        <p className="text-xs text-muted">{t("collectLabel")}</p>
        {cod > 0 ? (
          <p className="font-mono text-2xl font-semibold text-text">{formatK(cod, { locale })}</p>
        ) : (
          <p className="text-sm font-medium text-text">
            {order.cod ? t("codZero") : t("prepaidCollectNothing")}
          </p>
        )}
      </div>

      <dl className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <dt className="text-xs text-muted">{t("customer")}</dt>
          <dd className="text-sm text-text">{order.customer_display_name ?? "—"}</dd>
          {phone ? (
            <dd className="flex flex-wrap items-center gap-2">
              <a
                href={`tel:${phone}`}
                className="inline-flex min-h-11 items-center font-mono text-sm text-primary underline-offset-2 hover:underline"
              >
                {phone}
              </a>
              <CopyButton value={phone} label={t("copyPhone")} />
              <a
                href={`https://wa.me/${digits(phone)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-primary hover:bg-bg-2"
              >
                {t("whatsapp")}
              </a>
            </dd>
          ) : (
            <dd className="text-sm text-muted">{t("noPhone")}</dd>
          )}
        </div>

        {order.fulfilment === "delivery" ? (
          <div className="space-y-1">
            <dt className="text-xs text-muted">{t("dropoff")}</dt>
            {dropoff ? (
              <>
                <dd className="text-sm text-text" data-testid="dropoff-text">
                  {dropoff.text}
                </dd>
                <dd className="flex flex-wrap items-center gap-2">
                  {addressCopy ? <CopyButton value={addressCopy} label={t("copyAddress")} /> : null}
                  {dropoff.mapsUrl ? (
                    <a
                      href={dropoff.mapsUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-primary hover:bg-bg-2"
                    >
                      {t("openMap")}
                    </a>
                  ) : (
                    <span className="text-xs text-muted">{t("noGps")}</span>
                  )}
                </dd>
              </>
            ) : (
              <dd className="space-y-1 text-sm text-muted">
                <span>
                  {dispatch && !messageFailed ? t("loadingAddress") : t("addressNotOnOrder")}
                </span>
                {!dispatch ? (
                  <Link
                    href={`/${locale}/orders/dispatch`}
                    className="block min-h-11 text-primary underline-offset-2 hover:underline"
                  >
                    {t("openDispatchBoard")}
                  </Link>
                ) : null}
                {messageFailed ? (
                  <span className="block text-warning">{t("addressFailed")}</span>
                ) : null}
              </dd>
            )}
          </div>
        ) : null}
      </dl>

      {dispatch ? (
        <div
          className="space-y-1 rounded-md border border-border bg-bg p-3"
          data-testid="rider-info"
        >
          <p className="text-xs text-muted">{t("rider")}</p>
          <p className="text-sm font-medium text-text">
            {dispatch.courier_name}{" "}
            <span className="text-xs font-normal text-muted">
              {t(`dispatchStatus.${dispatch.status}`)}
            </span>
          </p>
          {dispatch.courier_reference ? (
            <p className="font-mono text-xs text-muted">
              {t("courierRef", { ref: dispatch.courier_reference })}
            </p>
          ) : null}
          {courier?.contact_whatsapp_e164 ? (
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-text">{courier.contact_whatsapp_e164}</span>
              <CopyButton value={courier.contact_whatsapp_e164} label={t("copyRiderPhone")} />
            </p>
          ) : null}
          {rawMessage ? (
            <details className="pt-1">
              <summary className="min-h-11 cursor-pointer py-3 text-xs font-medium text-primary">
                {t("courierMessage")}
              </summary>
              <pre className="whitespace-pre-wrap break-words rounded bg-surface p-2 text-xs text-text-2">
                {rawMessage}
              </pre>
              <CopyButton value={rawMessage} label={t("copyCourierMessage")} />
            </details>
          ) : null}
        </div>
      ) : order.fulfilment === "delivery" ? (
        <p className="text-xs text-muted">{t("noRiderYet")}</p>
      ) : null}
    </section>
  );
}
