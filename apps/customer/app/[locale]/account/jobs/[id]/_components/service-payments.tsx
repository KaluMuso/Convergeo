"use client";

import { createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { useSession } from "../../../../../../lib/customer-session";

export type ServiceObligation = {
  id: string;
  checkout_group_id: string;
  leg: string;
  amount_ngwee: number;
  status: string;
  payment_id: string | null;
  can_pay: boolean;
};

export function ServicePayments({
  jobId,
  refreshKey = 0,
}: {
  jobId: string;
  refreshKey?: number;
}) {
  const t = useTranslations("services.funding");
  const locale = useLocale();
  const router = useRouter();
  const { session } = useSession();
  const [legs, setLegs] = useState<ServiceObligation[]>([]);
  const [phone, setPhone] = useState("");
  const [rail, setRail] = useState("mtn");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const client = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => session?.access_token ?? null,
      }),
    [session?.access_token],
  );
  const load = useCallback(async () => {
    try {
      setLegs(
        await client.request<ServiceObligation[]>(`/jobs/${jobId}/payments`),
      );
      setError(false);
    } catch {
      setError(true);
    }
  }, [client, jobId]);
  useEffect(() => {
    if (!session) return;
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load, refreshKey, session?.access_token]);
  const pay = async (leg: ServiceObligation) => {
    setBusy(true);
    setError(false);
    try {
      if (rail === "card") {
        const result = await client.request<{ payment_id: string }>(
          "/payments/card/session",
          {
            method: "POST",
            body: JSON.stringify({ checkout_group_id: leg.checkout_group_id }),
          },
        );
        router.push(`/${locale}/checkout/card/${result.payment_id}`);
      } else {
        await client.request("/payments/retry", {
          method: "POST",
          body: JSON.stringify({
            checkout_group_id: leg.checkout_group_id,
            payer_number: phone,
            rail,
          }),
        });
      }
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className="space-y-3 rounded border border-border p-4"
      aria-label={t("title")}
    >
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
              disabled={busy || (rail !== "card" && !phone.trim())}
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
              <input
                value={phone}
                type="tel"
                onChange={(e) => setPhone(e.target.value)}
              />
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
