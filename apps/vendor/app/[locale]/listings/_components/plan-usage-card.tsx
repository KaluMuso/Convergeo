"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type PlanSummary = {
  key: string;
  name: string;
  price_ngwee: number;
  max_listings: number | null;
  max_images_per_listing: number;
  featured_slots: number;
  analytics_depth: string;
  wholesale_tools: boolean;
};

export type VendorPlanStatus = {
  enabled: boolean;
  plan: PlanSummary | null;
  effective_max_listings: number | null;
  max_images_per_listing: number;
  listing_count: number;
  remaining_listings: number | null;
  at_limit: boolean;
  over_limit: boolean;
  limited_by: "plan" | "kyc" | "none";
  override_expires_at: string | null;
  upgrade_options: PlanSummary[];
};

type PlanUsageCardProps = {
  /** Change to re-fetch (e.g. after a listing is created). */
  refreshKey?: number;
};

/**
 * Plan usage + friendly upgrade prompt (flag `vendor_plans`). Renders nothing
 * when the flag is off or the status cannot be read: plans never block the
 * listings screen. Over the limit nothing is removed — the copy says so.
 */
export function PlanUsageCard({ refreshKey = 0 }: PlanUsageCardProps) {
  const t = useTranslations("vendor");
  const { session } = useSession();
  const [status, setStatus] = useState<VendorPlanStatus | null>(null);
  const token = session?.access_token ?? null;
  const client = useMemo(
    () => createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => token }),
    [token],
  );

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    client
      .request<VendorPlanStatus>("/vendor/plan")
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [client, refreshKey, token]);

  if (!status?.enabled || !status.plan) return null;

  const plan = status.plan;
  const price =
    plan.price_ngwee === 0
      ? t("plans.free")
      : t("plans.perMonth", { price: formatK(plan.price_ngwee) });
  const usage =
    status.effective_max_listings === null
      ? t("plans.usageUnlimited", { count: status.listing_count })
      : t("plans.usage", { count: status.listing_count, max: status.effective_max_listings });
  const showPrompt = status.at_limit && status.limited_by === "plan";

  return (
    <section
      data-testid="vendor-plan-card"
      aria-labelledby="vendor-plan-heading"
      className="flex flex-col gap-2 rounded-md border border-border bg-surface p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="vendor-plan-heading" className="text-base font-semibold text-text">
          {t("plans.heading", { name: plan.name })}
        </h2>
        <span className="text-sm text-text-2">{price}</span>
      </div>
      <p className="text-sm text-text">{usage}</p>
      {status.limited_by === "kyc" && status.at_limit ? (
        <p className="text-sm text-text-2">{t("plans.kycLimit")}</p>
      ) : null}
      {showPrompt ? (
        <div role="status" data-testid="vendor-plan-upgrade" className="flex flex-col gap-2">
          <p className="text-sm text-text">
            {status.over_limit ? t("plans.overLimit") : t("plans.atLimit")}
          </p>
          <p className="text-sm text-text-2">{t("plans.keepSelling")}</p>
          {status.upgrade_options.length > 0 ? (
            <ul className="flex list-none flex-col gap-1 p-0">
              {status.upgrade_options.map((option) => (
                <li key={option.key} className="text-sm text-text">
                  {option.max_listings === null
                    ? t("plans.optionUnlimited", {
                        name: option.name,
                        price: formatK(option.price_ngwee),
                      })
                    : t("plans.option", {
                        name: option.name,
                        price: formatK(option.price_ngwee),
                        max: option.max_listings,
                      })}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-sm text-text-2">{t("plans.howToUpgrade")}</p>
        </div>
      ) : null}
    </section>
  );
}
