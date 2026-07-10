"use client";

import { useTranslations } from "next-intl";

import type { RecentVerification } from "../_lib/recent-verifications";

type RecentVerificationsProps = {
  items: RecentVerification[];
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

export function RecentVerifications({ items }: RecentVerificationsProps) {
  const t = useTranslations("vendor");

  return (
    <section data-testid="scan-recent-list" aria-labelledby="scan-recent-heading">
      <h2
        id="scan-recent-heading"
        style={{
          margin: "0 0 var(--sp-2)",
          fontSize: "var(--fs-small)",
          fontWeight: 600,
          color: "var(--text-2)",
        }}
      >
        {t("scan.recent.heading")}
      </h2>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: "var(--fs-small)", color: "var(--text-3)" }}>
          {t("scan.recent.empty")}
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
              key={`${item.orderId}-${item.verifiedAt}`}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "var(--sp-2)",
                fontSize: "var(--fs-small)",
                padding: "var(--sp-2) var(--sp-3)",
                borderRadius: "var(--r)",
                background: "var(--surface-2)",
              }}
            >
              <span>{t("scan.recent.order", { orderId: item.orderId.slice(0, 8) })}</span>
              <span style={{ color: "var(--text-3)" }}>{formatTime(item.verifiedAt)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
