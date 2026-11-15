"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

import type {
  PlanSummary,
  VendorPlanStatus,
} from "../../listings/_components/plan-usage-card";

/**
 * Plan picker (flag `vendor_plans`): every active plan with its monthly price
 * and the annual prepay price (12 x monthly less the admin-set discount; the API
 * computes it in integer ngwee). Payments are off: changing plan is a request to
 * our team, so the picker only informs.
 */
export function PlanPicker({ locale }: { locale: string }) {
  const t = useTranslations("vendor.plans");
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const client = useMemo(
    () => createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => token }),
    [token],
  );
  const [status, setStatus] = useState<VendorPlanStatus | null | "error">(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    client
      .request<VendorPlanStatus>("/vendor/plan")
      .then((next) => !cancelled && setStatus(next))
      .catch(() => !cancelled && setStatus("error"));
    return () => {
      cancelled = true;
    };
  }, [client, token]);

  if (status === null)
    return <p className="text-sm text-text-2">{t("picker.loading")}</p>;
  if (status === "error" || !status.enabled) {
    return <p className="text-sm text-text-2">{t("picker.unavailable")}</p>;
  }

  return (
    <div className="space-y-3">
      {status.annual_discount_pct > 0 ? (
        <p className="m-0 text-sm text-text-2">
          {t("picker.annualNote", { pct: status.annual_discount_pct })}
        </p>
      ) : null}
      <ul
        className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2"
        data-testid="plan-picker"
      >
        {status.plans.map((plan) => (
          <PlanCard
            key={plan.key}
            plan={plan}
            current={status.plan?.key === plan.key}
            discountPct={status.annual_discount_pct}
          />
        ))}
      </ul>
      <p className="m-0 text-sm text-text-2">{t("howToUpgrade")}</p>
      <Link
        href={`/${locale}/extras`}
        className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
      >
        {t("picker.seeExtras")}
      </Link>
    </div>
  );
}

function PlanCard({
  plan,
  current,
  discountPct,
}: {
  plan: PlanSummary;
  current: boolean;
  discountPct: number;
}) {
  const t = useTranslations("vendor.plans");
  return (
    <li
      className={`flex flex-col gap-1 rounded-lg border bg-surface p-4 shadow-1 ${current ? "border-primary" : "border-border"}`}
      data-testid={`plan-${plan.key}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="m-0 text-base font-semibold text-text">{plan.name}</h2>
        {current ? (
          <span className="rounded-pill bg-primary-tint px-2 py-0.5 text-micro font-semibold text-primary">
            {t("picker.current")}
          </span>
        ) : null}
      </div>
      <p className="m-0 text-sm text-text">
        {plan.price_ngwee === 0
          ? t("free")
          : t("perMonth", { price: formatK(plan.price_ngwee) })}
      </p>
      {plan.price_ngwee > 0 && discountPct > 0 ? (
        <p
          className="m-0 text-sm text-text-2"
          data-testid={`plan-${plan.key}-annual`}
        >
          {t("picker.perYear", {
            price: formatK(plan.annual_price_ngwee),
            pct: discountPct,
          })}
        </p>
      ) : null}
      <p className="m-0 text-sm text-text-2">
        {plan.max_listings === null
          ? t("picker.listingsUnlimited")
          : t("picker.listings", { max: plan.max_listings })}
      </p>
    </li>
  );
}
