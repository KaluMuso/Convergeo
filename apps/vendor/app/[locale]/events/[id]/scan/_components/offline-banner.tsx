"use client";

import { useTranslations } from "next-intl";

type OfflineBannerProps = {
  lastSyncedAt: string | null;
};

function formatTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function OfflineBanner({ lastSyncedAt }: OfflineBannerProps) {
  const t = useTranslations("vendor");

  return (
    <div
      data-testid="event-scan-offline-banner"
      role="status"
      style={{
        borderRadius: "var(--r)",
        border: "1px solid var(--warning)",
        background: "color-mix(in srgb, var(--warning) 12%, var(--surface))",
        padding: "var(--sp-3)",
        color: "var(--text)",
        fontSize: "var(--fs-small)",
      }}
    >
      <p style={{ margin: 0, fontWeight: 600 }}>{t("scan.eventCheckIn.offline.title")}</p>
      <p style={{ margin: "var(--sp-1) 0 0", color: "var(--text-2)" }}>
        {t("scan.eventCheckIn.offline.body")}
      </p>
      <p style={{ margin: "var(--sp-1) 0 0", color: "var(--text-3)" }}>
        {lastSyncedAt
          ? t("scan.eventCheckIn.sync.lastSynced", { time: formatTime(lastSyncedAt) })
          : t("scan.eventCheckIn.sync.neverSynced")}
      </p>
    </div>
  );
}
