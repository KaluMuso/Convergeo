"use client";

import { useTranslations } from "next-intl";

import type { SignedDocUrl } from "./api";

type DocViewerProps = {
  documents: SignedDocUrl[];
  docsAvailable: boolean;
  /** Signed links expire; lets the reviewer fetch fresh ones. */
  onRefresh?: () => void;
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

export function DocViewer({ documents, docsAvailable, onRefresh }: DocViewerProps) {
  const t = useTranslations("admin.kyc.detail");

  if (!docsAvailable) {
    return (
      <p role="alert" className="text-sm text-warning">
        {t("docsUnavailable")}
      </p>
    );
  }

  if (documents.length === 0) {
    return <p className="text-sm text-muted">{t("noDocuments")}</p>;
  }

  const nrc = documents.find((doc) => doc.doc_type === "nrc");
  const selfie = documents.find((doc) => doc.doc_type === "selfie");
  const primary = [nrc, selfie].filter((doc): doc is SignedDocUrl => Boolean(doc));
  const shown = primary.length > 0 ? primary : documents;

  const renderDoc = (doc: SignedDocUrl) => (
    <figure key={doc.path} className="space-y-2" data-testid={`kyc-doc-${doc.doc_type}`}>
      <figcaption className="flex items-center justify-between gap-2 text-sm font-medium text-text">
        <span>{docLabel(doc.doc_type, t)}</span>
        {doc.signed_url ? (
          <a
            href={doc.signed_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center text-xs font-medium text-primary underline-offset-2 hover:underline"
          >
            {t("openFullSize")}
          </a>
        ) : null}
      </figcaption>
      {doc.signed_url ? (
        <img
          alt={docLabel(doc.doc_type, t)}
          className="max-h-[28rem] w-full rounded-md border border-border bg-bg object-contain"
          src={doc.signed_url}
        />
      ) : (
        <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted">
          {t("noPreview")}
        </p>
      )}
    </figure>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">{t("docsExpired")}</p>
        {onRefresh ? (
          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium"
          >
            {t("refreshDocs")}
          </button>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2">{shown.map(renderDoc)}</div>
    </div>
  );
}
