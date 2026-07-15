"use client";

import { useTranslations } from "next-intl";

type ScanCountProps = {
  checkedInCount: number;
  pendingCount: number;
};

export function ScanCount({ checkedInCount, pendingCount }: ScanCountProps) {
  const t = useTranslations("vendor");

  return (
    <div
      data-testid="event-scan-count"
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        borderRadius: "var(--r)",
        background: "var(--bg-2)",
        padding: "var(--sp-3) var(--sp-4)",
      }}
    >
      <span style={{ fontFamily: "var(--font-display)", fontSize: "var(--fs-h3)" }}>
        {t("scan.eventCheckIn.count.checkedIn", { count: checkedInCount })}
      </span>
      {pendingCount > 0 ? (
        <span
          data-testid="event-scan-pending-count"
          style={{ fontSize: "var(--fs-small)", color: "var(--warning)" }}
        >
          {t("scan.eventCheckIn.count.pending", { count: pendingCount })}
        </span>
      ) : null}
    </div>
  );
}
