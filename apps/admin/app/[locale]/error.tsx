"use client";

import { useReportClientError } from "@vergeo/observability";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { getApiBaseUrl } from "../../lib/api-base-url";
import { reloadOnceForChunkError } from "../../lib/chunk-reload";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

/**
 * Route error boundary. Renders inside the admin shell (the layout survives), so the
 * operator keeps navigation; the failure is reported (same sink as customer/vendor) and a
 * stale-deploy chunk 404 recovers with a single guarded reload instead of a dead end.
 */
export default function ErrorBoundary({ error, reset }: ErrorProps) {
  const t = useTranslations("common");
  const params = useParams();
  const locale = typeof params?.locale === "string" ? params.locale : "en";

  useEffect(() => {
    reloadOnceForChunkError(error);
  }, [error]);

  useReportClientError(
    error,
    { boundary: "route", application: "admin" },
    { apiBaseUrl: getApiBaseUrl(), locale },
  );

  return (
    <div
      role="alert"
      className="mx-auto flex w-full max-w-xl flex-col items-start gap-3 py-10"
      data-testid="admin-route-error"
    >
      <h1 className="text-lg font-semibold text-text">{t("errorPage.heading")}</h1>
      <p className="text-sm text-muted">{t("errorPage.body")}</p>
      <button
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
        onClick={reset}
        type="button"
      >
        {t("errorPage.retry")}
      </button>
    </div>
  );
}
