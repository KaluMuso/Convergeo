import { LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { getAccountListSession } from "../_components/account-list-server";
import { getAccountTranslator } from "../_components/account-server";

import { fetchPoints, progressPercent } from "./rewards-api";

import type { Metadata } from "next";

export const metadata: Metadata = { robots: { index: false, follow: false } };

type PageProps = {
  params: Promise<{ locale: string }>;
};

/** Convergeo Points (flag `loyalty_points`): server-rendered, zero client JS. */
export default async function AccountRewardsPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const { accessToken } = await getAccountListSession(locale);
  const points = await fetchPoints(accessToken);
  if (!points) notFound();

  const t = await getAccountTranslator(locale);
  const percent = progressPercent(points.balance, points.next_coupon_threshold);
  const dateFormat = new Intl.DateTimeFormat(locale, { dateStyle: "medium" });

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("rewards.title")}</h2>
        <p className="text-sm text-text-2">{t("rewards.description")}</p>
      </header>

      <div className="space-y-3 rounded border border-border bg-surface p-4">
        <p className="text-sm text-text-2">{t("rewards.balanceLabel")}</p>
        <p className="font-display text-h2 text-display-ink">
          {t("rewards.balance", { points: points.balance })}
        </p>
        <div
          role="progressbar"
          aria-label={t("rewards.progressAria")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="h-2 w-full overflow-hidden rounded bg-border"
        >
          <div className="h-full bg-primary" style={{ width: `${percent}%` }} />
        </div>
        <p className="text-sm text-text-2">
          {t("rewards.progress", { remaining: points.points_to_next })}
        </p>
        <p className="text-xs text-text-2">{t("rewards.redeemSoon")}</p>
      </div>

      <section className="space-y-3">
        <h3 className="font-display text-h3 text-display-ink">{t("rewards.historyTitle")}</h3>
        {points.history.length === 0 ? (
          <p className="text-sm text-text-2">{t("rewards.historyEmpty")}</p>
        ) : (
          <ul className="divide-y divide-border rounded border border-border bg-surface">
            {points.history.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-3 p-3 text-sm">
                <span>
                  <span className="block text-display-ink">
                    {t(`rewards.reason.${entry.reason}`)}
                  </span>
                  <span className="block text-xs text-text-2">
                    {dateFormat.format(new Date(entry.created_at))}
                  </span>
                </span>
                <span className="font-mono text-display-ink">
                  {entry.points > 0 ? `+${entry.points}` : `${entry.points}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h3 className="font-display text-h3 text-display-ink">{t("rewards.howTitle")}</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-text-2">
          <li>{t("rewards.howOrders")}</li>
          <li>{t("rewards.howReviews")}</li>
          <li>{t("rewards.howRules")}</li>
        </ul>
      </section>
    </section>
  );
}
