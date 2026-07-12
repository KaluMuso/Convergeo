"use client";

import { useTranslations } from "next-intl";

import type { SignedDocUrl } from "./api";

type DocViewerProps = {
  documents: SignedDocUrl[];
  docsAvailable: boolean;
};

function docLabel(
  docType: SignedDocUrl["doc_type"],
  t: ReturnType<typeof useTranslations<"admin.kyc.detail">>,
) {
  if (docType === "nrc") {
    return t("nrc");
  }
  if (docType === "selfie") {
    return t("selfie");
  }
  return t("otherDoc");
}

export function DocViewer({ documents, docsAvailable }: DocViewerProps) {
  const t = useTranslations("admin.kyc.detail");

  if (!docsAvailable) {
    return <p className="text-sm text-warning">{t("docsUnavailable")}</p>;
  }

  const nrc = documents.find((doc) => doc.doc_type === "nrc");
  const selfie = documents.find((doc) => doc.doc_type === "selfie");
  const primary = [nrc, selfie].filter((doc): doc is SignedDocUrl => Boolean(doc));

  const renderDoc = (doc: SignedDocUrl) => (
    <figure key={doc.path} className="space-y-2">
      <figcaption className="text-sm font-medium text-text">{docLabel(doc.doc_type, t)}</figcaption>
      {doc.signed_url ? (
        <img
          alt={docLabel(doc.doc_type, t)}
          className="max-h-80 w-full rounded-md border border-border object-contain bg-bg"
          src={doc.signed_url}
        />
      ) : (
        <p className="text-sm text-muted">{t("noPreview")}</p>
      )}
    </figure>
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">{t("docsExpired")}</p>
      {primary.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">{primary.map(renderDoc)}</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">{documents.map(renderDoc)}</div>
      )}
    </div>
  );
}
