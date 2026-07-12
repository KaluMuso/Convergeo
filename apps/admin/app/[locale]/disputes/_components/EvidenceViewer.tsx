"use client";

import { useTranslations } from "next-intl";

import type { SignedEvidenceUrl } from "./api";

type EvidenceViewerProps = {
  evidence: SignedEvidenceUrl[];
  evidenceAvailable: boolean;
};

function isImagePath(path: string): boolean {
  const lowered = path.toLowerCase();
  return (
    lowered.endsWith(".jpg") ||
    lowered.endsWith(".jpeg") ||
    lowered.endsWith(".png") ||
    lowered.endsWith(".webp")
  );
}

export function EvidenceViewer({ evidence, evidenceAvailable }: EvidenceViewerProps) {
  const t = useTranslations("admin.disputes.detail.evidence");

  if (!evidenceAvailable) {
    return <p className="text-sm text-muted">{t("unavailable")}</p>;
  }

  if (evidence.length === 0) {
    return <p className="text-sm text-muted">{t("empty")}</p>;
  }

  const customerEvidence = evidence.filter((item) => item.side === "customer");
  const vendorEvidence = evidence.filter((item) => item.side === "vendor");

  const renderItem = (item: SignedEvidenceUrl) => (
    <li key={item.path} className="space-y-2 rounded-md border border-border p-3">
      <p className="text-xs text-muted">{item.path.split("/").pop()}</p>
      {item.signed_url ? (
        isImagePath(item.path) ? (
          <img
            alt={item.path}
            className="max-h-64 w-full rounded-md object-contain"
            src={item.signed_url}
          />
        ) : (
          <a
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
            href={item.signed_url}
            rel="noopener noreferrer"
            target="_blank"
          >
            {t("openDocument")}
          </a>
        )
      ) : (
        <p className="text-sm text-muted">{t("noPreview")}</p>
      )}
      {item.expires_at ? (
        <p className="text-xs text-muted">
          {t("expires", { at: new Date(item.expires_at).toLocaleString() })}
        </p>
      ) : null}
    </li>
  );

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">{t("customer")}</h3>
        {customerEvidence.length === 0 ? (
          <p className="text-sm text-muted">{t("noneCustomer")}</p>
        ) : (
          <ul className="space-y-3">{customerEvidence.map(renderItem)}</ul>
        )}
      </section>
      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">{t("vendor")}</h3>
        {vendorEvidence.length === 0 ? (
          <p className="text-sm text-muted">{t("noneVendor")}</p>
        ) : (
          <ul className="space-y-3">{vendorEvidence.map(renderItem)}</ul>
        )}
      </section>
    </div>
  );
}
