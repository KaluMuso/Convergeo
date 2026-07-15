"use client";

import { useTranslations } from "next-intl";

export type RecentScanStatus = "checked_in" | "pending" | "conflict" | "rejected";

export type RecentScanItem = {
  ticketId: string;
  scannedAt: string;
  status: RecentScanStatus;
};

type RecentScansProps = {
  items: RecentScanItem[];
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

const STATUS_COLOR: Record<RecentScanStatus, string> = {
  checked_in: "var(--success)",
  pending: "var(--warning)",
  conflict: "var(--danger)",
  rejected: "var(--danger)",
};

export function RecentScans({ items }: RecentScansProps) {
  const t = useTranslations("vendor");

  return (
    <section data-testid="event-scan-recent-list" aria-labelledby="event-scan-recent-heading">
      <h2
        id="event-scan-recent-heading"
        style={{
          margin: "0 0 var(--sp-2)",
          fontSize: "var(--fs-small)",
          fontWeight: 600,
          color: "var(--text-2)",
        }}
      >
        {t("scan.eventCheckIn.recent.heading")}
      </h2>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: "var(--fs-small)", color: "var(--text-3)" }}>
          {t("scan.eventCheckIn.recent.empty")}
        </p>
      ) : (
        <ul
          style={{
            margin: 0,
            padding: 0,
            listStyle: "none",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-2)",
          }}
        >
          {items.map((item) => (
            <li
              key={`${item.ticketId}-${item.scannedAt}`}
              data-testid="event-scan-recent-item"
              data-status={item.status}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "var(--sp-2)",
                fontSize: "var(--fs-small)",
                padding: "var(--sp-2) var(--sp-3)",
                borderRadius: "var(--r)",
                background: "var(--bg-2)",
                borderLeft: `3px solid ${STATUS_COLOR[item.status]}`,
              }}
            >
              <span>
                {t("scan.eventCheckIn.recent.ticket", { ticketId: item.ticketId.slice(0, 8) })}
              </span>
              <span style={{ color: "var(--text-3)" }}>{formatTime(item.scannedAt)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
