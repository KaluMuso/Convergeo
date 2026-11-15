"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { useAdminPermissions } from "../../../../lib/roles-api";
import { useAnalyticsNavEnabled } from "../../_components/use-analytics-nav";

import { visibleTabs, type AnyAnalyticsTab } from "./dashboards-data";

/**
 * One tab bar for every analytics screen. Tabs follow the caller's grants (revenue needs
 * finance.read/operate, the rest analytics.read); the four v2 behaviour tabs appear only
 * while `/admin/analytics/status` reports analytics_v2_rollups ON.
 */
export function AnalyticsTabs({ locale, active }: { locale: string; active: AnyAnalyticsTab }) {
  const t = useTranslations("admin.analytics");
  const grants = useAdminPermissions();
  const v2Enabled = useAnalyticsNavEnabled(true);
  const tabs = visibleTabs(grants, v2Enabled);
  return (
    <nav aria-label={t("tabs.label")} className="flex flex-wrap gap-2">
      {tabs.map((entry) => {
        const current = entry.tab === active;
        return (
          <Link
            key={entry.tab}
            href={`/${locale}/${entry.href}`}
            aria-current={current ? "page" : undefined}
            className={[
              "inline-flex min-h-11 items-center rounded-md border px-3 text-sm font-medium",
              current
                ? "border-primary bg-surface text-primary"
                : "border-border bg-surface text-text hover:border-primary",
            ].join(" ")}
          >
            {t(`tabs.${entry.tab}`)}
          </Link>
        );
      })}
    </nav>
  );
}
