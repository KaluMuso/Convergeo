"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  DEFAULT_COUNTRY_CODE,
  formatE164,
  isValidZambianMobile,
} from "../../../(auth)/_components/auth-utils";
import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { useSession } from "../../../../../lib/customer-session";
import { loadTicketOrder, type TicketOrder } from "../_lib/ticket-checkout";

import type { CheckoutShellLabels } from "./step-fulfilment";

type PaymentOption = "momo" | "card";
type PaymentOptions = {
  session_id: string;
  total_ngwee: number;
  available_methods: string[];
};
type PaymentStatus = {
  checkout_group_id: string;
  order_id: string;
  payment_id: string | null;
  status: string;
  rail: string | null;
  amount_ngwee: number;
  cod: boolean;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function TicketCheckout({
  locale,
  groupId,
  retry = false,
  labels,
  loginLabel,
  payLabel,
  retryLabel,
  cancelledLabel,
  expiredLabel,
  ordersLabel,
}: {
  locale: string;
  groupId: string | null;
  retry?: boolean;
  labels: CheckoutShellLabels;
  loginLabel: string;
  payLabel: string;
  retryLabel: string;
  cancelledLabel: string;
  expiredLabel: string;
  ordersLabel: string;
}) {
  const router = useRouter();
  const session = useSession();
  const submitting = useRef(false);
  const sessionRef = useRef(session);
  const groupRef = useRef(groupId);
  sessionRef.current = session;
  groupRef.current = groupId;
  const [order, setOrder] = useState<TicketOrder | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [buyerId, setBuyerId] = useState<string | null>(null);
  const [methods, setMethods] = useState<PaymentOption[]>([]);
  const [method, setMethod] = useState<PaymentOption>("momo");
  const [rail, setRail] = useState<"mtn" | "airtel">("mtn");
  const [lockedRail, setLockedRail] = useState<"mtn" | "airtel" | null>(null);
  const [number, setNumber] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pendingHref = `/${locale}/checkout/pending/${groupId}?ticket=1`;
  const ready =
    order &&
    token === session.session?.access_token &&
    buyerId === session.session?.user?.id &&
    !session.loading;

  useEffect(() => {
    setError(null);
    setLoading(true);
    setOrder(null);
    setToken(null);
    setBuyerId(null);
    setMethods([]);
    setLockedRail(null);
    setBusy(false);
    submitting.current = false;
    if (!groupId || !UUID.test(groupId)) {
      setError(labels.error);
      setLoading(false);
      return;
    }
    if (session.loading) return;
    if (!session.session?.access_token || !session.session.user?.id) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const accessToken = session.session.access_token;
    const userId = session.session.user.id;
    const api = createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => accessToken });
    void (async () => {
      try {
        const db = await getBrowserClient();
        const ticket = await loadTicketOrder(db, groupId, userId, true);
        // A refresh after initiation resumes the existing attempt instead of creating another.
        let status: PaymentStatus | null = null;
        try {
          status = await api.request<PaymentStatus>(
            `/payments/status?group=${encodeURIComponent(groupId)}`,
          );
        } catch (cause) {
          if (!(cause instanceof ApiError && cause.code === "payment.not_found")) throw cause;
        }
        if (status) {
          if (
            status.checkout_group_id !== groupId ||
            status.order_id !== ticket.orderId ||
            status.amount_ngwee !== ticket.totalNgwee ||
            status.cod ||
            !status.payment_id ||
            !UUID.test(status.payment_id) ||
            !["card", "mtn", "airtel"].includes(status.rail ?? "")
          ) {
            throw new Error("Payment linkage is invalid");
          }
          if (retry && ["cancelled", "expired"].includes(status.status)) {
            // The current claim contract does not permit a new attempt after
            // cancellation/expiry. Keep the buyer on this ticket group without a CTA.
            if (!cancelled) setError(status.status === "cancelled" ? cancelledLabel : expiredLabel);
            return;
          }
          if (
            retry &&
            ["card", "mtn", "airtel"].includes(status.rail ?? "") &&
            status.status === "failed"
          ) {
            // A terminal attempt returns here explicitly. The existing API
            // still decides if its claim can be retried.
          } else {
            if (!cancelled) {
              router.replace(
                status.rail === "card" && status.payment_id && status.status !== "success"
                  ? `/${locale}/checkout/card/${status.payment_id}?group=${groupId}`
                  : pendingHref,
              );
            }
            return;
          }
        }
        if (ticket.status !== "pending") throw new Error("Ticket checkout is no longer active");
        const options = await api.request<PaymentOptions>(
          `/checkout/steps/payment-options?session_id=${encodeURIComponent(groupId)}`,
        );
        if (
          options.session_id !== groupId ||
          options.total_ngwee !== ticket.totalNgwee ||
          !Array.isArray(options.available_methods)
        ) {
          throw new Error("Payment options do not match ticket order");
        }
        const allowed = (["momo", "card"] as const)
          .filter((m) => options.available_methods.includes(m))
          .filter((m) =>
            !retry || !status ? true : status.rail === "card" ? m === "card" : m === "momo",
          );
        if (!allowed.length) throw new Error("No online payment method is available");
        if (!cancelled) {
          if (retry && (status?.rail === "mtn" || status?.rail === "airtel")) {
            setRail(status.rail);
            setLockedRail(status.rail);
          }
          setOrder(ticket);
          setToken(accessToken);
          setBuyerId(userId);
          setMethods(allowed);
          setMethod(allowed[0]!);
        }
      } catch {
        if (!cancelled) setError(labels.error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    cancelledLabel,
    expiredLabel,
    groupId,
    labels.error,
    locale,
    pendingHref,
    retry,
    router,
    session.loading,
    session.session,
  ]);

  const pay = async () => {
    if (
      submitting.current ||
      !ready ||
      !order ||
      !token ||
      !methods.includes(method) ||
      (lockedRail && rail !== lockedRail)
    )
      return;
    const stillCurrent = () =>
      groupRef.current === order.groupId &&
      sessionRef.current.session?.access_token === token &&
      sessionRef.current.session?.user?.id === buyerId;
    if (method === "momo" && !isValidZambianMobile(number)) {
      setError(number.trim() ? labels.payment.invalidPayer : labels.payment.required);
      return;
    }
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const api = createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => token });
      const payer = method === "momo" ? formatE164(DEFAULT_COUNTRY_CODE, number) : undefined;
      const validated = await api.request<{
        session_id: string;
        method: string;
        total_ngwee: number;
      }>("/checkout/steps/payment", {
        method: "POST",
        body: JSON.stringify({
          session_id: order.groupId,
          method,
          ...(method === "momo" ? { rail, payer_number: payer } : {}),
        }),
      });
      if (
        validated.session_id !== order.groupId ||
        validated.method !== method ||
        validated.total_ngwee !== order.totalNgwee
      ) {
        throw new Error("Payment validation did not match ticket order");
      }
      if (!stillCurrent()) return;
      if (method === "card") {
        const card = await api.request<{
          checkout_group_id: string;
          payment_id: string;
          amount_ngwee: number;
        }>("/payments/card/session", {
          method: "POST",
          body: JSON.stringify({ checkout_group_id: order.groupId }),
        });
        if (
          card.checkout_group_id !== order.groupId ||
          card.amount_ngwee !== order.totalNgwee ||
          !UUID.test(card.payment_id)
        ) {
          throw new Error("Card session did not match ticket order");
        }
        if (!stillCurrent()) return;
        router.replace(`/${locale}/checkout/card/${card.payment_id}?group=${order.groupId}`);
      } else {
        const started = await api.request<{
          checkout_group_id: string;
          payment_id: string;
          order_count: number;
        }>("/payments/retry", {
          method: "POST",
          body: JSON.stringify({ checkout_group_id: order.groupId, payer_number: payer, rail }),
        });
        if (
          started.checkout_group_id !== order.groupId ||
          !UUID.test(started.payment_id) ||
          started.order_count !== 1
        ) {
          throw new Error("Payment attempt did not match ticket order");
        }
        if (!stillCurrent()) return;
        router.replace(pendingHref);
      }
    } catch {
      setError(labels.payment.error);
      submitting.current = false;
      setBusy(false);
    }
  };

  return (
    <section className="space-y-6 p-4" data-testid="ticket-checkout">
      <h1 className="text-2xl font-semibold">{labels.pageTitle}</h1>
      {loading || session.loading ? <p>{labels.loading}</p> : null}
      {!loading && !session.loading && !session.session ? (
        <Link
          href={`/${locale}/login?next=${encodeURIComponent(`/${locale}/checkout?group=${groupId ?? ""}`)}`}
        >
          {loginLabel}
        </Link>
      ) : null}
      {ready && !loading ? (
        <>
          <div className="rounded-card border border-border p-4">
            <p>
              {order.title} × {order.qty}
            </p>
            <p className="font-semibold">
              {labels.review.total}: {formatK(order.totalNgwee)}
            </p>
          </div>
          <fieldset className="space-y-3" disabled={busy}>
            <legend className="font-semibold">{labels.payment.title}</legend>
            {methods.includes("momo") ? (
              <label className="block">
                <input
                  type="radio"
                  name="ticket-payment"
                  checked={method === "momo"}
                  onChange={() => setMethod("momo")}
                />{" "}
                {labels.payment.momo}
              </label>
            ) : null}
            {methods.includes("card") ? (
              <label className="block">
                <input
                  type="radio"
                  name="ticket-payment"
                  checked={method === "card"}
                  onChange={() => setMethod("card")}
                />{" "}
                {labels.payment.card}
              </label>
            ) : null}
            {method === "momo" ? (
              <>
                <label className="block">
                  {labels.payment.railMtn}
                  <input
                    type="radio"
                    name="ticket-rail"
                    checked={rail === "mtn"}
                    disabled={lockedRail === "airtel"}
                    onChange={() => setRail("mtn")}
                  />
                </label>
                <label className="block">
                  {labels.payment.railAirtel}
                  <input
                    type="radio"
                    name="ticket-rail"
                    checked={rail === "airtel"}
                    disabled={lockedRail === "mtn"}
                    onChange={() => setRail("airtel")}
                  />
                </label>
                <label className="block" htmlFor="ticket-payer">
                  {labels.payment.payerLabel}
                </label>
                <input
                  id="ticket-payer"
                  type="tel"
                  autoComplete="tel-national"
                  className="w-full rounded-card border border-border p-3"
                  placeholder={labels.payment.payerPlaceholder}
                  value={number}
                  onChange={(event) => setNumber(event.target.value)}
                />
              </>
            ) : (
              <p>{labels.payment.cardExplainer}</p>
            )}
          </fieldset>
          <Button
            type="button"
            onClick={() => void pay()}
            loading={busy}
            loadingLabel={labels.payment.loading}
          >
            {busy ? labels.payment.loading : retry ? retryLabel : payLabel}
          </Button>
        </>
      ) : null}
      {error ? (
        <p role="alert" className="text-danger">
          {error}
        </p>
      ) : null}
      <Link
        href={ready ? `/${locale}/account/orders/${order.orderId}` : `/${locale}/account/orders`}
      >
        {ordersLabel}
      </Link>
    </section>
  );
}
