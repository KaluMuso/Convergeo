"use client";

import { createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { customerAuth, useSession } from "../../../../../../lib/customer-session";

export type ServiceObligation = {
  id: string;
  job_id: string;
  order_id: string;
  checkout_group_id: string;
  leg: string;
  amount_ngwee: number;
  status: string;
  payment_id: string | null;
  can_pay: boolean;
};

export const CHECKOUT_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type ExactCardPayment = {
  payment_id: string;
  checkout_group_id: string;
  order_id: string;
  amount_ngwee: number;
  rail: string;
  cod: boolean;
};

export function matchesCardPayment(
  payment: ExactCardPayment,
  expected: {
    paymentId: string;
    groupId: string;
    orderId: string;
    amountNgwee: number;
  },
): boolean {
  return (
    payment.payment_id === expected.paymentId &&
    CHECKOUT_UUID.test(expected.groupId) &&
    payment.checkout_group_id === expected.groupId &&
    CHECKOUT_UUID.test(expected.orderId) &&
    payment.order_id === expected.orderId &&
    payment.rail === "card" &&
    payment.cod === false &&
    Number.isSafeInteger(expected.amountNgwee) &&
    expected.amountNgwee > 0 &&
    Number.isSafeInteger(payment.amount_ngwee) &&
    payment.amount_ngwee === expected.amountNgwee
  );
}

/** Read-only resolution. The job hint is useful only after both authorized reads agree. */
export async function resolveServiceCardContext(
  client: ReturnType<typeof createApiClient>,
  jobId: string,
  paymentId: string,
  isCurrent: () => boolean,
) {
  if (!CHECKOUT_UUID.test(jobId) || !CHECKOUT_UUID.test(paymentId) || !isCurrent())
    throw new Error("invalid_service_context");
  const obligations = await client.request<ServiceObligation[]>(`/jobs/${jobId}/payments`);
  if (!isCurrent()) throw new Error("stale_service_context");
  const matches = Array.isArray(obligations)
    ? obligations.filter((leg) => leg.job_id === jobId && leg.payment_id === paymentId)
    : [];
  const leg = matches[0];
  if (matches.length !== 1 || !leg || !leg.id || !["deposit", "balance"].includes(leg.leg))
    throw new Error("invalid_service_obligation");
  const expected = {
    paymentId,
    groupId: leg.checkout_group_id,
    orderId: leg.order_id,
    amountNgwee: leg.amount_ngwee,
  };
  // `payment` selects this exact attempt; a group read could silently select a newer attempt.
  const payment = await client.request<ExactCardPayment>(
    `/payments/status?payment=${encodeURIComponent(paymentId)}`,
  );
  if (!isCurrent() || !matchesCardPayment(payment, expected))
    throw new Error("invalid_service_payment");
  // can_pay authorizes fresh initiation only, not reading an already pending attempt.
  return { kind: "service" as const, jobId, obligationId: leg.id, leg: leg.leg, ...expected };
}

export function ServicePayments(props: { jobId: string; refreshKey?: number }) {
  const { session, generation, loading, error } = useSession();
  if (!session || loading || error) return null;
  return (
    <IdentityServicePayments
      key={`${generation}:${session.user.id}:${props.jobId}`}
      {...props}
      userId={session.user.id}
      authGeneration={generation}
    />
  );
}

function IdentityServicePayments({
  jobId,
  refreshKey = 0,
  userId,
  authGeneration,
}: {
  jobId: string;
  refreshKey?: number;
  userId: string;
  authGeneration: number;
}) {
  const t = useTranslations("services.funding");
  const locale = useLocale();
  const router = useRouter();
  const [legs, setLegs] = useState<ServiceObligation[]>([]);
  const [phone, setPhone] = useState("");
  const [rail, setRail] = useState("mtn");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const active = useRef(false);
  const inFlight = useRef(false);
  const initiated = useRef(new Map<string, { paymentId: string; groupId: string }>());
  const readSequence = useRef(0);
  const mutationEpoch = useRef(0);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const isCurrent = useCallback(() => {
    const auth = customerAuth.snapshot();
    return (
      active.current &&
      !auth.loading &&
      !auth.error &&
      auth.generation === authGeneration &&
      auth.session?.user.id === userId
    );
  }, [authGeneration, userId]);
  const client = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () =>
          isCurrent() ? (customerAuth.snapshot().session?.access_token ?? null) : null,
      }),
    [isCurrent],
  );
  const load = useCallback(async () => {
    if (!isCurrent()) return;
    const request = ++readSequence.current;
    const epoch = mutationEpoch.current;
    const current = () =>
      isCurrent() && request === readSequence.current && epoch === mutationEpoch.current;
    try {
      const result = await client.request<ServiceObligation[]>(`/jobs/${jobId}/payments`);
      if (!current()) return;
      for (const leg of result) {
        const attempt = initiated.current.get(leg.id);
        if (
          attempt &&
          leg.status === "failed" &&
          leg.can_pay &&
          leg.payment_id === attempt.paymentId &&
          leg.checkout_group_id === attempt.groupId
        ) {
          initiated.current.delete(leg.id);
        }
      }
      setLegs(result);
      setError(false);
    } catch {
      if (current()) setError(true);
    }
  }, [client, jobId, isCurrent]);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load, refreshKey]);
  const pay = async (leg: ServiceObligation) => {
    if (!isCurrent() || inFlight.current || !leg.can_pay || initiated.current.has(leg.id)) return;
    inFlight.current = true;
    // Earlier reads must not restore retry permission across an initiation.
    mutationEpoch.current += 1;
    setBusy(true);
    setError(false);
    try {
      if (rail === "card") {
        const result = await client.request<{ payment_id: string }>("/payments/card/session", {
          method: "POST",
          body: JSON.stringify({ checkout_group_id: leg.checkout_group_id }),
        });
        if (!isCurrent()) return;
        if (!result.payment_id) throw new Error("missing_payment_attempt");
        initiated.current.set(leg.id, {
          paymentId: result.payment_id,
          groupId: leg.checkout_group_id,
        });
        mutationEpoch.current += 1;
        router.push(
          `/${locale}/checkout/card/${encodeURIComponent(result.payment_id)}?job=${encodeURIComponent(jobId)}`,
        );
      } else {
        const result = await client.request<{ payment_id: string }>("/payments/retry", {
          method: "POST",
          body: JSON.stringify({
            checkout_group_id: leg.checkout_group_id,
            payer_number: phone,
            rail,
          }),
        });
        if (!isCurrent()) return;
        if (!result.payment_id) throw new Error("missing_payment_attempt");
        initiated.current.set(leg.id, {
          paymentId: result.payment_id,
          groupId: leg.checkout_group_id,
        });
        mutationEpoch.current += 1;
      }
      if (!isCurrent()) return;
      await load();
    } catch {
      mutationEpoch.current += 1;
      if (isCurrent()) setError(true);
    } finally {
      if (isCurrent()) setBusy(false);
      inFlight.current = false;
    }
  };
  return (
    <section className="space-y-3 rounded border border-border p-4" aria-label={t("title")}>
      <h3>{t("title")}</h3>
      {legs.map((leg) => (
        <div key={leg.id} className="space-y-2">
          <p>
            {t(leg.leg)}: {formatK(leg.amount_ngwee)}
          </p>
          <p role="status">{t(`status.${leg.status}`)}</p>
          {leg.can_pay && (
            <Button
              loadingLabel={t("pay")}
              disabled={busy || initiated.current.has(leg.id) || (rail !== "card" && !phone.trim())}
              onClick={() => void pay(leg)}
            >
              {t(leg.status === "failed" ? "retry" : "pay")}
            </Button>
          )}
        </div>
      ))}
      {legs.some((leg) => leg.can_pay) && (
        <>
          <label>
            {t("rail")}
            <select value={rail} onChange={(e) => setRail(e.target.value)}>
              <option value="mtn">{t("mtn")}</option>
              <option value="airtel">{t("airtel")}</option>
              <option value="card">{t("card")}</option>
            </select>
          </label>
          {rail !== "card" && (
            <label>
              {t("phone")}
              <input value={phone} type="tel" onChange={(e) => setPhone(e.target.value)} />
            </label>
          )}
        </>
      )}
      {error && <p role="alert">{t("error")}</p>}
      <Button loadingLabel={t("refresh")} onClick={() => void load()}>
        {t("refresh")}
      </Button>
    </section>
  );
}
