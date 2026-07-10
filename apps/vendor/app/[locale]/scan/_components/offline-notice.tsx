"use client";

import { useTranslations } from "next-intl";

type OfflineNoticeProps = {
  className?: string;
};

export function OfflineNotice({ className }: OfflineNoticeProps) {
  const t = useTranslations("vendor");

  return (
    <div
      className={className}
      data-testid="scan-offline-notice"
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
      <p style={{ margin: 0, fontWeight: 600 }}>{t("scan.offline.title")}</p>
      <p style={{ margin: "var(--sp-1) 0 0", color: "var(--text-2)" }}>{t("scan.offline.body")}</p>
    </div>
  );
}
