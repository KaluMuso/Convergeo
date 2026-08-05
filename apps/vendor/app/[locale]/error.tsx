"use client";

import { useReportClientError } from "@vergeo/observability";
import { useParams } from "next/navigation";

import { getApiBaseUrl } from "../../lib/api-base-url";
import { resolveErrorPageCopy } from "../../lib/error-page-copy";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorBoundary({ error, reset }: ErrorProps) {
  const params = useParams();
  const locale = typeof params?.locale === "string" ? params.locale : "en";
  const copy = resolveErrorPageCopy(locale);

  useReportClientError(
    error,
    {
      boundary: "route",
      application: "vendor",
    },
    {
      apiBaseUrl: getApiBaseUrl(),
      locale,
    },
  );

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
      <p aria-hidden="true" className="font-mono text-4xl font-bold text-primary">
        {copy.code}
      </p>
      <h1 className="text-lg font-semibold text-text">{copy.heading}</h1>
      <p className="text-sm text-text-2">{copy.body}</p>
      <button
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium text-text"
        onClick={reset}
        type="button"
      >
        {copy.retry}
      </button>
    </main>
  );
}
